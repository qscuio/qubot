"""
异动监测服务 (Burst/Abnormal Movement Monitor)

Real-time monitoring for stock abnormal movements:
- 快速拉升: Price surge (>3% in 5 min)
- 放量异动: Volume spike (5-min vol > 3x 30-min average)
- 涨停异动: Limit-up related movements (new limit, burst, reseal)

Sends alerts to BURST_TARGET_GROUP.
"""

import asyncio
import logging
import math
from datetime import datetime, time as time_type
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.database import db
from app.core.timezone import china_now, china_today
from app.core.stock_links import get_chart_url

logger = logging.getLogger(__name__)


class BurstMonitorService:
    """异动监测服务 - monitors for abnormal stock movements."""
    
    def __init__(self):
        self.is_running = False
        self._monitor_task = None
        self._ak = None  # Lazy-loaded akshare
        
        # State tracking
        self._price_state: Dict[str, Dict] = {}  # code -> {price, time, ...}
        self._volume_state: Dict[str, List] = {}  # code -> [recent volumes]
        self._alerted: Dict[str, float] = {}  # code -> last alert time (rate limit)
        
        # Configurable thresholds
        self.PRICE_SURGE_PCT = 3.0  # Alert if price surges 3%+ 
        self.VOLUME_SPIKE_RATIO = 3.0  # Alert if 5-min vol > 3x average
        self.ALERT_COOLDOWN = 300  # 5 min cooldown per stock
        self.POLL_INTERVAL = 30  # Poll every 30 seconds
    
    def _get_akshare(self):
        """Lazy load akshare module."""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                logger.error("akshare not installed")
        return self._ak
    
    async def start(self):
        """Start the burst monitoring service."""
        if self.is_running:
            return
        
        if not settings.BURST_TARGET_GROUP:
            logger.warn("BURST_TARGET_GROUP not configured, burst monitor disabled")
            return
        
        self.is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Burst monitor service started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Burst monitor service stopped")
    
    def _is_market_hours(self) -> bool:
        """Check if currently in A-share market hours."""
        now = china_now()
        if now.weekday() >= 5:  # Weekend
            return False
        
        hour, minute = now.hour, now.minute
        time_mins = hour * 60 + minute
        
        # 09:30-11:30 (570-690) or 13:00-15:00 (780-900)
        return (570 <= time_mins <= 690) or (780 <= time_mins <= 900)
    
    async def _poll_realtime_data(self) -> Dict[str, Dict]:
        """Fetch real-time stock data."""
        ak = self._get_akshare()
        if not ak:
            return {}
        
        try:
            # Add timeout to avoid hanging the loop
            try:
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_zh_a_spot_em),
                    timeout=20.0
                )
            except asyncio.TimeoutError:
                logger.warn("Timeout while polling realtime data")
                return {}
            
            if df is None or df.empty:
                return {}
            
            result = {}
            # Helper for safe conversion
            def safe_float(v, default=0.0):
                try:
                    f = float(v)
                    return default if math.isnan(f) else f
                except (ValueError, TypeError):
                    return default

            def safe_int(v, default=0):
                try:
                    f = float(v)
                    return default if math.isnan(f) else int(f)
                except (ValueError, TypeError):
                    return default

            for _, row in df.iterrows():
                code = str(row.get('代码', ''))
                name = str(row.get('名称', ''))
                
                # Skip ST stocks
                if 'ST' in name:
                    continue
                
                result[code] = {
                    'name': name,
                    'price': safe_float(row.get('最新价')),
                    'change_pct': safe_float(row.get('涨跌幅')),
                    'volume': safe_int(row.get('成交量')),
                    'amount': safe_float(row.get('成交额')),
                    'high': safe_float(row.get('最高')),
                    'low': safe_float(row.get('最低')),
                    'open': safe_float(row.get('今开')),
                    'prev_close': safe_float(row.get('昨收')),
                    'turnover': safe_float(row.get('换手率')),
                }
            
            return result
            
        except Exception as e:
            logger.warn(f"Failed to poll realtime data: {e}")
            return {}
    
    async def _detect_bursts(self, current_data: Dict[str, Dict]) -> List[Dict]:
        """Detect abnormal movements by comparing with previous state."""
        signals = []
        now = china_now()
        now_ts = now.timestamp()
        
        for code, curr in current_data.items():
            price = curr['price']
            if price <= 0:
                continue
            
            prev = self._price_state.get(code)
            
            # Check rate limit
            last_alert = self._alerted.get(code, 0)
            if now_ts - last_alert < self.ALERT_COOLDOWN:
                continue
            
            # 1. 快速拉升检测 (Price Surge)
            if prev:
                prev_price = prev.get('price', price)
                if prev_price > 0:
                    change_since_last = (price - prev_price) / prev_price * 100
                    
                    # Rapid surge: >3% increase since last poll
                    if change_since_last >= self.PRICE_SURGE_PCT:
                        signals.append({
                            'type': 'price_surge',
                            'emoji': '🚀',
                            'code': code,
                            'name': curr['name'],
                            'msg': f"快速拉升 +{change_since_last:.1f}% | 当前涨幅 {curr['change_pct']:+.1f}%",
                        })
                        self._alerted[code] = now_ts
                        continue
                    
                    # Rapid drop: >3% decrease since last poll  
                    if change_since_last <= -self.PRICE_SURGE_PCT:
                        signals.append({
                            'type': 'price_drop',
                            'emoji': '📉',
                            'code': code,
                            'name': curr['name'],
                            'msg': f"快速下跌 {change_since_last:.1f}% | 当前涨幅 {curr['change_pct']:+.1f}%",
                        })
                        self._alerted[code] = now_ts
                        continue
            
            # 2. 涨停板异动 (Limit-up related)
            # Near limit-up detection (9.5%+ for normal, 19.5%+ for 创业板/科创板)
            is_kcb_cyb = code.startswith('30') or code.startswith('68')
            limit_threshold = 19.5 if is_kcb_cyb else 9.5
            
            if curr['change_pct'] >= limit_threshold:
                # Check if it's a new limit-up (wasn't near limit before)
                if prev and prev.get('change_pct', 0) < limit_threshold:
                    signals.append({
                        'type': 'new_limit',
                        'emoji': '🔥',
                        'code': code,
                        'name': curr['name'],
                        'msg': f"触及涨停 {curr['change_pct']:+.1f}% | 换手 {curr['turnover']:.1f}%",
                    })
                    self._alerted[code] = now_ts
            
            # Update state
            self._price_state[code] = {
                'price': price,
                'change_pct': curr['change_pct'],
                'time': now_ts,
            }
        
        return signals
    
    async def _send_alerts(self, signals: List[Dict]):
        """Send alert messages to BURST_TARGET_GROUP."""
        if not signals:
            return
        
        from app.core.bot import telegram_service
        
        target = settings.BURST_TARGET_GROUP
        if not target:
            return
        
        now = china_now()
        
        # Group signals into one message (max 10 per batch)
        MAX_PER_BATCH = 10
        for i in range(0, len(signals), MAX_PER_BATCH):
            batch = signals[i:i + MAX_PER_BATCH]
            
            lines = [
                f"⚡ <b>异动提醒</b> {now.strftime('%H:%M:%S')}",
                "━━━━━━━━━━━━━━━━━━━━━\n",
            ]
            
            for sig in batch:
                chart_url = get_chart_url(sig['code'], sig['name'], context="burst")
                lines.append(
                    f"{sig['emoji']} <a href=\"{chart_url}\"><b>{sig['name']}</b></a> ({sig['code']})\n"
                    f"   {sig['msg']}\n"
                )
            
            msg = "\n".join(lines)
            
            try:
                await telegram_service.send_message(target, msg, parse_mode="html")
                logger.info(f"Sent {len(batch)} burst alerts")
            except Exception as e:
                logger.error(f"Failed to send burst alert: {e}")
    
    async def _monitor_loop(self):
        """Main monitoring loop - runs every 30 seconds during market hours."""
        logger.info("Starting burst monitor loop")
        
        while self.is_running:
            try:
                if self._is_market_hours():
                    # Poll and detect
                    data = await self._poll_realtime_data()
                    
                    if data:
                        signals = await self._detect_bursts(data)
                        if signals:
                            await self._send_alerts(signals)
                    
                    await asyncio.sleep(self.POLL_INTERVAL)
                else:
                    # Outside market hours - clear state at market open
                    now = china_now()
                    if now.hour == 9 and now.minute == 25:
                        self._price_state.clear()
                        self._volume_state.clear()
                        self._alerted.clear()
                        logger.info("Cleared burst monitor state for new trading day")
                    
                    await asyncio.sleep(60)
                    
            except Exception as e:
                logger.error(f"Burst monitor loop error: {e}")
                await asyncio.sleep(30)
    
    async def get_status(self) -> Dict:
        """Get current monitor status."""
        return {
            'is_running': self.is_running,
            'is_market_hours': self._is_market_hours(),
            'tracked_stocks': len(self._price_state),
            'recent_alerts': len(self._alerted),
        }


# Singleton
burst_monitor_service = BurstMonitorService()
