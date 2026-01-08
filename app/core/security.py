"""
Security Middleware for FastAPI

Provides:
- Rate limiting per IP
- Suspicious path blocking
- Request logging for security analysis
"""

import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logger import Logger

logger = Logger("Security")


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
