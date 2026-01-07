from aiogram.types import BotCommand

from app.bots.bot_spec import BotSpec

AGENT_BOT_COMMANDS = [
    BotCommand(command="start", description="Main menu"),
    BotCommand(command="chats", description="My chats"),
    BotCommand(command="new", description="New chat"),
    BotCommand(command="rename", description="Rename chat"),
    BotCommand(command="clear", description="Clear chat"),
    BotCommand(command="providers", description="AI providers"),
    BotCommand(command="models", description="Model selection"),
    BotCommand(command="agent", description="List or switch agents"),
    BotCommand(command="tools", description="List tools"),
    BotCommand(command="tool", description="Run a tool"),
    BotCommand(command="skills", description="List skills"),
    BotCommand(command="export", description="Export chat"),
    BotCommand(command="think", description="Toggle thinking"),
    BotCommand(command="status", description="Status"),
    BotCommand(command="advstatus", description="Advanced status"),
    BotCommand(command="help", description="Help"),
    BotCommand(command="ask", description="Ask with agents"),
]

AGENT_BOT = BotSpec(
    name="agent-bot",
    token_attr="AGENT_BOT_TOKEN",
    router_module="app.bots.ai.handlers_advanced",
    commands=AGENT_BOT_COMMANDS,
)
