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
    BotCommand(command="first", description="首板(收盘封板)"),
    BotCommand(command="burst", description="曾涨停(炸板)"),
    BotCommand(command="streak", description="连板榜"),
    BotCommand(command="strong", description="强势股"),
    BotCommand(command="watch", description="启动追踪"),
    BotCommand(command="scan", description="信号扫描"),
    BotCommand(command="sync", description="同步涨停"),
    # User management commands
    BotCommand(command="useradd", description="添加用户"),
    BotCommand(command="userdel", description="删除用户"),
    BotCommand(command="userlist", description="用户列表"),
    BotCommand(command="help", description="帮助"),
]

CRAWLER_BOT = BotSpec(
    name="crawler-bot",
    token_attr="CRAWLER_BOT_TOKEN",
    router_module="app.bots.crawler.handlers",
    commands=CRAWLER_BOT_COMMANDS,
)

