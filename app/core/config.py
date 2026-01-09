import os
from pydantic_settings import BaseSettings
from pydantic import field_validator, Field
from typing import List, Optional

def parse_comma_list(v):
    """Parse comma-separated string into list. 'none' means empty/no filtering."""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        # Treat 'none' as no filtering
        if v.strip().lower() == 'none':
            return []
        return [x.strip() for x in v.split(',') if x.strip() and x.strip().lower() != 'none']
    return []

class Settings(BaseSettings):
    # Telegram Sessions (JSON format)
    # Format: [{"session": "...", "api_id": 123, "api_hash": "...", "master": true}, ...]
    SESSIONS_JSON: Optional[str] = Field(default=None, validation_alias='TG_SESSIONS_JSON')
    
    # Bot Tokens (from @BotFather)
    MONITOR_BOT_TOKEN: Optional[str] = None
    AI_BOT_TOKEN: Optional[str] = None
    RSS_BOT_TOKEN: Optional[str] = None
    BOT_TOKEN: Optional[str] = None  # Legacy single token
    AGENT_BOT_TOKEN: Optional[str] = None
    CRAWLER_BOT_TOKEN: Optional[str] = None
    
    # Crawler settings
    CRAWLER_INTERVAL_MS: int = 3600000  # 1 hour default
    ENABLE_CRAWLER: bool = True
    
    # Webhook
    WEBHOOK_URL: Optional[str] = None
    BOT_SECRET: Optional[str] = None
    BOT_PORT: int = 10001
    API_PORT: int = 10002
    DOMAIN: Optional[str] = None
    
    # App Settings
    LOG_LEVEL: str = "INFO"
    RATE_LIMIT_MS: Optional[int] = 1000
    RSS_POLL_INTERVAL_MS: Optional[int] = 300000

    @field_validator('RATE_LIMIT_MS', 'RSS_POLL_INTERVAL_MS', 'BOT_PORT', 'API_PORT', mode='before')
    @classmethod
    def parse_optional_int(cls, v, info):
        if v is None or v == '':
            defaults = {'RATE_LIMIT_MS': 1000, 'RSS_POLL_INTERVAL_MS': 300000, 'BOT_PORT': 10001, 'API_PORT': 10002}
            return defaults.get(info.field_name)
        return int(v)
    
    # Monitoring - stored as comma-separated strings to avoid pydantic-settings JSON parsing
    SOURCE_CHANNELS: Optional[str] = None
    TARGET_CHANNEL: Optional[str] = None
    VIP_TARGET_CHANNEL: Optional[str] = None  # Separate channel for VIP user messages
    REPORT_TARGET_CHANNEL: Optional[str] = None  # Separate channel for daily reports
    STOCK_ALERT_CHANNEL: Optional[str] = None  # Channel for limit-up stock alerts
    ALERT_CHANNEL: Optional[str] = None  # Channel for security alerts
    
    # Limit-Up Tracker settings
    ENABLE_LIMIT_UP: bool = True
    ENABLE_SECTOR: bool = True  # Sector analysis tracking
    KEYWORDS: Optional[str] = None
    FROM_USERS: Optional[str] = None
    ALLOWED_USERS: Optional[str] = None
    BLACKLIST_CHANNELS: Optional[str] = None  # Channels/groups to exclude from forwarding and reports
    
    # Summarization settings
    MONITOR_SUMMARIZE: bool = True  # Enable message summarization
    MONITOR_BUFFER_SIZE: int = 200   # Summarize after N messages
    MONITOR_BUFFER_TIMEOUT: int = 7200  # Summarize after N seconds (2 hours)
    
    # Message Compression Pipeline
    COMPRESSOR_MIN_LENGTH: int = 15  # Minimum message length
    COMPRESSOR_MAX_MESSAGES: int = 200  # Max messages after compression
    COMPRESSOR_SCORE_THRESHOLD: float = 0.2  # Minimum quality score
    
    # Message Deduplication
    DEDUP_CACHE_SIZE: int = 5000  # Max fingerprints to store
    DEDUP_SIMILARITY_THRESHOLD: float = 0.85  # Minimum similarity to consider duplicate (0.0-1.0)
    
    # Twitter monitoring
    TWITTER_ACCOUNTS: Optional[str] = None  # JSON array of Twitter accounts

    @property
    def source_channels_list(self) -> list:
        return parse_comma_list(self.SOURCE_CHANNELS)

    @property
    def sessions_list(self) -> List[dict]:
        """
        Parse SESSIONS_JSON into a list of dicts.
        Format: [{"session": "...", "api_id": 123, "api_hash": "..."}]
        """
        if not self.SESSIONS_JSON:
            return []
        try:
            import json
            result = json.loads(self.SESSIONS_JSON)
            return result if isinstance(result, list) else []
        except Exception as e:
            # Log the error for debugging
            print(f"[Config] Failed to parse SESSIONS_JSON: {e}")
            return []

    @property
    def keywords_list(self) -> list:
        return parse_comma_list(self.KEYWORDS)

    @property
    def from_users_list(self) -> list:
        return parse_comma_list(self.FROM_USERS)

    @property
    def allowed_users_list(self) -> list:
        if not self.ALLOWED_USERS:
            return []
        if isinstance(self.ALLOWED_USERS, str):
            return [int(x.strip()) for x in self.ALLOWED_USERS.split(',') if x.strip()]
        return []
    
    @property
    def blacklist_channels_list(self) -> list:
        return parse_comma_list(self.BLACKLIST_CHANNELS)

    # Database
    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # AI - Support multiple naming conventions
    AI_PROVIDER: str = "groq"
    AI_MODEL: Optional[str] = None
    # Primary keys (new naming)
    AI_API_KEY: Optional[str] = None
    # Provider-specific keys (from .env.example)
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    CLAUDE_API_KEY: Optional[str] = None
    NVIDIA_API_KEY: Optional[str] = None
    GLM_API_KEY: Optional[str] = None
    MINIMAX_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None

    def get_ai_key(self, provider: str = None) -> Optional[str]:
        """Get API key for the specified or default provider."""
        provider = provider or self.AI_PROVIDER
        mapping = {
            'openai': self.OPENAI_API_KEY or self.AI_API_KEY,
            'groq': self.GROQ_API_KEY,
            'gemini': self.GEMINI_API_KEY,
            'claude': self.CLAUDE_API_KEY,
            'nvidia': self.NVIDIA_API_KEY,
            'glm': self.GLM_API_KEY,
            'minimax': self.MINIMAX_API_KEY,
            'openrouter': self.OPENROUTER_API_KEY,
        }
        return mapping.get(provider.lower())
    
    # GitHub Export
    NOTES_REPO: Optional[str] = None
    GIT_SSH_KEY_PATH: Optional[str] = None
    GIT_SSH_COMMAND: Optional[str] = None
    GIT_KNOWN_HOSTS: Optional[str] = None

    # Feature Flags
    ENABLE_RSS: bool = True
    ENABLE_AI: bool = True
    ENABLE_MONITOR: bool = True
    API_ENABLED: bool = True
    
    # Advanced AI Settings
    AI_ADVANCED_PROVIDER: Optional[str] = "groq"  # Provider for advanced AI (default: groq)
    AI_EXTENDED_THINKING: bool = False  # Enable Claude extended thinking
    SEARX_URL: Optional[str] = None  # SearXNG URL for web search tool
    GITHUB_TOKEN: Optional[str] = None  # GitHub token for GitHub tools
    CLOUDFLARE_API_TOKEN: Optional[str] = None  # Cloudflare API token
    CLOUDFLARE_ACCOUNT_ID: Optional[str] = None  # Cloudflare account ID
    AI_ALLOWED_PATHS: Optional[str] = None  # Comma-separated allowed paths for file tools
    
    # API Keys (format: key1:userId1,key2:userId2)
    API_KEYS: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore unknown env vars

settings = Settings()
