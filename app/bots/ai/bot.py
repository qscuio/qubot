from aiogram.types import BotCommand

from app.bots.bot_spec import BotSpec

AI_BOT_COMMANDS = [
    BotCommand(command="start", description="Main menu"),
    BotCommand(command="chats", description="My chats"),
    BotCommand(command="new", description="New chat"),
    BotCommand(command="providers", description="AI providers"),
    BotCommand(command="models", description="Model selection"),
    BotCommand(command="export", description="Export chat"),
    BotCommand(command="status", description="Bot status"),
    BotCommand(command="rename", description="Rename chat"),
    BotCommand(command="clear", description="Clear chat"),
    BotCommand(command="help", description="Help"),
]

AI_BOT = BotSpec(
    name="ai-bot",
    token_attr="AI_BOT_TOKEN",
    router_module="app.bots.ai.handlers",
    commands=AI_BOT_COMMANDS,
)
