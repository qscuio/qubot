"""
Centralized Timezone Utilities

All date/time operations in this project should use Asia/Shanghai timezone
since the application deals with the Chinese stock market.
"""

import pytz
from datetime import datetime, date as date_type


# Standard timezone for the project
CHINA_TZ = pytz.timezone("Asia/Shanghai")

# Alias for backward compatibility
SHANGHAI_TZ = CHINA_TZ


def china_now() -> datetime:
    """Get current datetime in China timezone.
    
    Use this instead of datetime.now() throughout the project.
    """
    return datetime.now(CHINA_TZ)


def china_today() -> date_type:
    """Get current date in China timezone.
    
    Use this instead of date.today() throughout the project.
    """
    return datetime.now(CHINA_TZ).date()


def china_strftime(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get formatted current time string in China timezone."""
    return datetime.now(CHINA_TZ).strftime(fmt)
