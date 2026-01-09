"""
Security Middleware for FastAPI

Provides:
- Rate limiting per IP
- Suspicious path blocking
- Request logging for security analysis
- Firewall-level blocking via iptables
"""

import asyncio
import os
import subprocess
import time
from collections import defaultdict
from typing import Dict, Set, Tuple
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logger import Logger

logger = Logger("Security")

# Enable/disable iptables blocking (requires root or sudo permissions)
ENABLE_IPTABLES_BLOCKING = os.getenv("ENABLE_IPTABLES_BLOCKING", "false").lower() == "true"

# Channel to send security alerts to
ALERT_CHANNEL = os.getenv("ALERT_CHANNEL")

# Keep track of IPs already blocked at firewall level to avoid duplicate rules
_firewall_blocked_ips: Set[str] = set()

# Keep track of IPs already notified to avoid spam
_notified_ips: Set[str] = set()


async def send_attack_notification(ip: str, reason: str, path: str = None, count: int = None):
    """
    Send a notification about an attack to the configured alert channel.
    This runs asynchronously to avoid blocking the request.
    """
    if not ALERT_CHANNEL:
        logger.debug("No ALERT_CHANNEL configured, skipping notification")
        return
    
    # Avoid duplicate notifications for the same IP
    if ip in _notified_ips:
        return
    _notified_ips.add(ip)
    
    try:
        from app.core.bot import telegram_service
        
        message = f"🚨 <b>Security Alert</b>\n\n"
        message += f"<b>IP:</b> <code>{ip}</code>\n"
        message += f"<b>Reason:</b> {reason}\n"
        if path:
            message += f"<b>Path:</b> <code>{path}</code>\n"
        if count:
            message += f"<b>Suspicious requests:</b> {count}\n"
        message += f"<b>Action:</b> IP blocked"
        
        if ENABLE_IPTABLES_BLOCKING and ip in _firewall_blocked_ips:
            message += " (firewall + app)"
        else:
            message += " (app level)"
        
        await telegram_service.send_message(ALERT_CHANNEL, message, parse_mode="html")
        logger.info(f"📨 Sent attack notification for {ip} to {ALERT_CHANNEL}")
        
    except Exception as e:
        logger.error(f"Failed to send attack notification: {e}")


def block_ip_with_iptables(ip: str) -> bool:
    """
    Block an IP at the firewall level using iptables.
    Command: iptables -I INPUT 1 -s <IP> -j REJECT --reject-with icmp-host-unreachable
    
    Returns True if successful, False otherwise.
    """
    if not ENABLE_IPTABLES_BLOCKING:
        logger.debug(f"iptables blocking disabled, skipping firewall block for {ip}")
        return False
    
    # Skip if already blocked at firewall level
    if ip in _firewall_blocked_ips:
        logger.debug(f"IP {ip} already blocked at firewall level")
        return True
    
    # Validate IP format (basic check to prevent command injection)
    import re
    if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip):
        logger.error(f"Invalid IP format for iptables blocking: {ip}")
        return False
    
    try:
        cmd = [
            "iptables", "-I", "INPUT", "1",
            "-s", ip,
            "-j", "REJECT",
            "--reject-with", "icmp-host-unreachable"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            _firewall_blocked_ips.add(ip)
            logger.warn(f"🔥 Firewall blocked IP: {ip} via iptables")
            return True
        else:
            logger.error(f"iptables failed for {ip}: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"iptables command timed out for {ip}")
        return False
    except PermissionError:
        logger.error(f"Permission denied running iptables - need root/sudo")
        return False
    except Exception as e:
        logger.error(f"Failed to block {ip} with iptables: {e}")
        return False


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, requests_per_minute: int = 60, block_duration: int = 300):
        self.requests_per_minute = requests_per_minute
        self.block_duration = block_duration  # seconds
        self._requests: Dict[str, list] = defaultdict(list)
        self._blocked: Dict[str, float] = {}  # ip -> unblock_time
    
    def is_blocked(self, ip: str) -> bool:
        if ip in self._blocked:
            if time.time() < self._blocked[ip]:
                return True
            else:
                del self._blocked[ip]
        return False
    
    def block(self, ip: str, duration: int = None):
        self._blocked[ip] = time.time() + (duration or self.block_duration)
        logger.warn(f"🚫 Blocked IP: {ip} for {duration or self.block_duration}s")
        # Also block at firewall level if enabled
        block_ip_with_iptables(ip)
    
    def check(self, ip: str) -> Tuple[bool, int]:
        """
        Check if request is allowed.
        Returns (allowed: bool, remaining: int)
        """
        if self.is_blocked(ip):
            return False, 0
        
        now = time.time()
        minute_ago = now - 60
        
        # Clean old requests
        self._requests[ip] = [t for t in self._requests[ip] if t > minute_ago]
        
        # Check limit
        if len(self._requests[ip]) >= self.requests_per_minute:
            self.block(ip)
            return False, 0
        
        # Record request
        self._requests[ip].append(now)
        remaining = self.requests_per_minute - len(self._requests[ip])
        
        return True, remaining


# Suspicious paths that indicate vulnerability scanning
SUSPICIOUS_PATTERNS = [
    # IIS exploits
    '.htr', 'iisadmpwd', 'iisadmin',
    # PHP exploits
    '.php3', '.php4', '.php5', '.php6', '.phtml',
    # Script exploits
    '.asp', '.aspx', '.cfm', '.cgi', '.pl',
    # Admin panels
    'phpmyadmin', 'wp-admin', 'wp-login', 'administrator',
    'admin.php', 'login.php', 'setup.php',
    # Config files
    '.env', '.git', '.svn', '.htaccess', 'web.config',
    # Shell uploads
    'shell', 'c99', 'r57', 'webshell',
    # Common scanner patterns
    'niet', 'eval-stdin', 'phpunit',
]


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Security middleware that:
    1. Rate limits requests per IP
    2. Blocks suspicious scanner requests
    3. Logs security events
    """
    
    def __init__(self, app, rate_limiter: RateLimiter = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter()
        self._scanner_ips: Dict[str, int] = defaultdict(int)  # ip -> suspicious_count
    
    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP (considering proxies)."""
        # Check X-Forwarded-For header first (for reverse proxy)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Check X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct connection
        return request.client.host if request.client else "unknown"
    
    def _is_suspicious_path(self, path: str) -> bool:
        """Check if path looks like a vulnerability scan."""
        path_lower = path.lower()
        return any(pattern in path_lower for pattern in SUSPICIOUS_PATTERNS)
    
    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        path = request.url.path
        
        # Check if IP is blocked
        if self.rate_limiter.is_blocked(client_ip):
            logger.debug(f"🚫 Blocked request from {client_ip}: {path}")
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests. Please try again later."}
            )
        
        # Check for suspicious paths
        if self._is_suspicious_path(path):
            self._scanner_ips[client_ip] += 1
            logger.warn(f"🔍 Scanner detected from {client_ip}: {path} (count: {self._scanner_ips[client_ip]})")
            
            # Auto-block after 5 suspicious requests
            if self._scanner_ips[client_ip] >= 5:
                self.rate_limiter.block(client_ip, duration=3600)  # Block for 1 hour
                # Send attack notification in background
                asyncio.create_task(send_attack_notification(
                    ip=client_ip,
                    reason="Vulnerability scanner detected",
                    path=path,
                    count=self._scanner_ips[client_ip]
                ))
                return JSONResponse(
                    status_code=403,
                    content={"error": "Access denied."}
                )
            
            # Return 404 immediately without processing
            return JSONResponse(
                status_code=404,
                content={"error": "Not found."}
            )
        
        # Rate limit check
        allowed, remaining = self.rate_limiter.check(client_ip)
        if not allowed:
            # Send rate limit notification in background
            asyncio.create_task(send_attack_notification(
                ip=client_ip,
                reason="Rate limit exceeded",
                path=path
            ))
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded. Please try again later."}
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
        return response


# Global rate limiter instance
rate_limiter = RateLimiter(
    requests_per_minute=120,  # 120 requests per minute per IP
    block_duration=300  # Block for 5 minutes
)
