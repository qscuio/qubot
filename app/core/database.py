import asyncpg
import redis.asyncio as redis
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("Database")

class Database:
    def __init__(self):
        self.pool: asyncpg.Pool = None
        self.redis: redis.Redis = None

    async def connect(self):
        # Postgres
        if settings.DATABASE_URL:
            try:
                self.pool = await asyncpg.create_pool(settings.DATABASE_URL)
                logger.info("✅ Connected to PostgreSQL")
                await self.init_db()
            except Exception as e:
                logger.error("Failed to connect to PostgreSQL", e)
        
        # Redis
        if settings.REDIS_URL:
            try:
                self.redis = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
                await self.redis.ping()
                logger.info("✅ Connected to Redis")
            except Exception as e:
                logger.error("Failed to connect to Redis", e)

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Closed PostgreSQL connection")
        if self.redis:
            await self.redis.close()
            logger.info("Closed Redis connection")

    async def init_db(self):
        """Initialize database tables if they don't exist."""
        if not self.pool:
            return
            
        async with self.pool.acquire() as conn:
            # Monitor Channels Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_channels (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    category TEXT DEFAULT 'market',
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Add category column if not exists (migration for existing DBs)
            await conn.execute("""
                ALTER TABLE monitor_channels 
                ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'market';
            """)
            
            # Monitor History Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_history (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    source TEXT,
                    source_id TEXT,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Monitor Filters Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_filters (
                    user_id TEXT PRIMARY KEY,
                    filters JSONB,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Monitor VIP Users Table (users to forward immediately)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_vip_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    name TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Monitor Blacklist Table (channels to ignore)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_blacklist (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Monitor Message Cache (for daily reports)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_message_cache (
                    id SERIAL PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT,
                    sender_name TEXT,
                    message_text TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Index for efficient queries by channel and time
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_channel 
                ON monitor_message_cache(channel_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_time 
                ON monitor_message_cache(created_at);
            """)

            # Twitter Follows Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS twitter_follows (
                    username TEXT PRIMARY KEY,
                    user_id TEXT,
                    last_tweet_id TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # RSS Sources Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rss_sources (
                    id SERIAL PRIMARY KEY,
                    link TEXT UNIQUE NOT NULL,
                    title TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # RSS Subscriptions Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rss_subscriptions (
                    user_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    rss_source_id INTEGER REFERENCES rss_sources(id) ON DELETE CASCADE,
                    PRIMARY KEY (user_id, chat_id, rss_source_id)
                );
            """)

            # RSS History Table (for deduplication)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rss_history (
                    hash_id TEXT PRIMARY KEY,
                    source_id INTEGER,
                    item_id TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Hot Words Table (daily word frequency)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS hot_words (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL,
                    word TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    category TEXT,
                    UNIQUE(date, word)
                );
            """)
            
            # Index for efficient hot words queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hot_words_date 
                ON hot_words(date);
            """)

            # Crawler Sources Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS crawler_sources (
                    id SERIAL PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    name TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    crawl_interval_mins INT DEFAULT 60,
                    last_crawled_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Crawler Items Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS crawler_items (
                    id SERIAL PRIMARY KEY,
                    source_id INTEGER REFERENCES crawler_sources(id) ON DELETE CASCADE,
                    url TEXT UNIQUE,
                    title TEXT,
                    content TEXT,
                    summary TEXT,
                    published_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Indexes for crawler
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_crawler_items_time 
                ON crawler_items(created_at DESC);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_crawler_items_source 
                ON crawler_items(source_id);
            """)

            # Limit-Up Stocks Table (涨停记录)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS limit_up_stocks (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    name TEXT,
                    date DATE NOT NULL,
                    close_price DECIMAL,
                    change_pct DECIMAL,
                    turnover_rate DECIMAL,
                    limit_times INT DEFAULT 1,
                    is_sealed BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(code, date)
                );
            """)
            
            # Add is_sealed column if not exists (migration for existing DBs)
            await conn.execute("""
                ALTER TABLE limit_up_stocks 
                ADD COLUMN IF NOT EXISTS is_sealed BOOLEAN DEFAULT TRUE;
            """)

            # Limit-Up Streaks Table (连板统计)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS limit_up_streaks (
                    id SERIAL PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT,
                    streak_count INT DEFAULT 1,
                    first_limit_date DATE,
                    last_limit_date DATE,
                    cycle_start DATE,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_limit_up_date 
                ON limit_up_stocks(date DESC);
            """)

            # Startup Watchlist (启动追踪 - 一个月内涨停过一次的股票)
            # 当同一股票在一个月内涨停第二次时剔除
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS startup_watchlist (
                    id SERIAL PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT,
                    first_limit_date DATE,
                    first_limit_price DECIMAL,
                    added_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Sector Daily Performance (板块每日表现)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sector_daily (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    date DATE NOT NULL,
                    change_pct DECIMAL,
                    close_price DECIMAL,
                    turnover DECIMAL,
                    leading_stock TEXT,
                    leading_stock_pct DECIMAL,
                    up_count INT,
                    down_count INT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(code, date)
                );
            """)
            
            # Index for sector daily queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sector_daily_date 
                ON sector_daily(date DESC);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sector_daily_type 
                ON sector_daily(type);
            """)

            # Sector Reports (板块报告)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sector_reports (
                    id SERIAL PRIMARY KEY,
                    report_type TEXT NOT NULL,
                    report_date DATE NOT NULL,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(report_type, report_date)
                );
            """)

            # Allowed Users Table (授权用户)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS allowed_users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    added_by BIGINT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Seed allowed users from env if not already in DB
            env_users = settings.allowed_users_list or []
            for user_id in env_users:
                await conn.execute("""
                    INSERT INTO allowed_users (user_id, username, added_by)
                    VALUES ($1, 'env', 0)
                    ON CONFLICT (user_id) DO NOTHING
                """, user_id)
            
            logger.info("Database tables initialized")

db = Database()


class CacheService:
    """Redis cache wrapper with convenience methods."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def get(self, key: str) -> str:
        if not self.redis:
            return None
        return await self.redis.get(key)
    
    async def set(self, key: str, value: str, ttl: int = None):
        if not self.redis:
            return
        if ttl:
            await self.redis.setex(key, ttl, value)
        else:
            await self.redis.set(key, value)
    
    async def delete(self, key: str):
        if not self.redis:
            return
        await self.redis.delete(key)
    
    async def get_json(self, key: str):
        import json
        data = await self.get(key)
        return json.loads(data) if data else None
    
    async def set_json(self, key: str, value, ttl: int = None):
        import json
        await self.set(key, json.dumps(value), ttl)
    
    async def incr(self, key: str) -> int:
        if not self.redis:
            return 0
        return await self.redis.incr(key)
    
    async def expire(self, key: str, ttl: int):
        if not self.redis:
            return
        await self.redis.expire(key, ttl)


def get_cache() -> CacheService:
    return CacheService(db.redis)
