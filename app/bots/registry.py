from typing import Optional
from aiogram import Bot

from app.bots.ai.agent_bot import AGENT_BOT
from app.bots.ai.bot import AI_BOT
from app.bots.crawler.bot import CRAWLER_BOT
from app.bots.file.bot import FILE_BOT
from app.bots.monitor.bot import MONITOR_BOT
from app.bots.rss.bot import RSS_BOT
from app.bots.vibe.bot import VIBE_BOT

BOT_SPECS = [
    MONITOR_BOT,
    AI_BOT,
    AGENT_BOT,
    RSS_BOT,
    CRAWLER_BOT,
    FILE_BOT,
    VIBE_BOT,
]


def get_bot(name: str) -> Optional[Bot]:
    """Get a Bot instance by name (e.g., 'crawler', 'monitor', 'ai').
    
    Args:
        name: Bot name (without '-bot' suffix, e.g., 'crawler' for 'crawler-bot')
    
    Returns:
        Bot instance if found, None otherwise
    """
    from app.bots.dispatcher import bot_dispatcher
    
    # Normalize name (allow both 'crawler' and 'crawler-bot')
    search_name = name if name.endswith('-bot') else f"{name}-bot"
    
    for app in bot_dispatcher.apps:
        if app.get('name') == search_name:
            return app.get('bot')
    
    return None
