from aiogram.types import BotCommand

from app.bots.bot_spec import BotSpec

RSS_BOT_COMMANDS = [
    BotCommand(command="start", description="Main menu"),
    BotCommand(command="list", description="List feeds"),
    BotCommand(command="sub", description="Subscribe feed"),
    BotCommand(command="unsub", description="Unsubscribe feed"),
    BotCommand(command="status", description="RSS status"),
    BotCommand(command="help", description="Help"),
]

RSS_BOT = BotSpec(
    name="rss-bot",
    token_attr="RSS_BOT_TOKEN",
    router_module="app.bots.rss.handlers",
    commands=RSS_BOT_COMMANDS,
)
