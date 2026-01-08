from aiogram.types import BotCommand

from app.bots.bot_spec import BotSpec
from app.core.config import settings

CRAWLER_BOT_COMMANDS = [
    BotCommand(command="start", description="主菜单"),
    # Crawler commands
    BotCommand(command="add", description="添加网站"),
    BotCommand(command="remove", description="删除网站"),
    BotCommand(command="list", description="网站列表"),
    BotCommand(command="crawl", description="立即爬取"),
    BotCommand(command="recent", description="最新内容"),
    # Limit-up commands
    BotCommand(command="today", description="今日涨停"),
    BotCommand(command="streak", description="连板榜"),
    BotCommand(command="strong", description="强势股"),
    BotCommand(command="sync", description="同步涨停"),
    BotCommand(command="help", description="帮助"),
]

CRAWLER_BOT = BotSpec(
    name="crawler-bot",
    token_attr="CRAWLER_BOT_TOKEN",
    router_module="app.bots.crawler.handlers",
    commands=CRAWLER_BOT_COMMANDS,
)

