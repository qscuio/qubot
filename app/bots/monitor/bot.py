from aiogram.types import BotCommand

from app.bots.bot_spec import BotSpec

MONITOR_BOT_COMMANDS = [
    BotCommand(command="start", description="Main menu"),
    BotCommand(command="status", description="Monitor status"),
    BotCommand(command="sources", description="List sources"),
    BotCommand(command="add", description="Add source"),
    BotCommand(command="clear", description="Clear sources"),
    BotCommand(command="vip", description="Add VIP user"),
    BotCommand(command="unvip", description="Remove VIP user"),
    BotCommand(command="vips", description="List VIPs"),
    BotCommand(command="history", description="View history"),
    BotCommand(command="twitter", description="Add Twitter"),
    BotCommand(command="untwitter", description="Remove Twitter"),
    BotCommand(command="twitters", description="List Twitters"),
    BotCommand(command="help", description="Help"),
]

MONITOR_BOT = BotSpec(
    name="monitor-bot",
    token_attr="MONITOR_BOT_TOKEN",
    router_module="app.bots.monitor.handlers",
    commands=MONITOR_BOT_COMMANDS,
)
