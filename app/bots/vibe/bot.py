from aiogram.types import BotCommand

from app.bots.bot_spec import BotSpec

VIBE_BOT_COMMANDS = [
    BotCommand(command="start", description="Show help"),
    BotCommand(command="vibe", description="Send to AI agent"),
    BotCommand(command="agent", description="Switch agent"),
    BotCommand(command="cwd", description="Working directory"),
    BotCommand(command="stop", description="Stop task"),
    BotCommand(command="clear", description="Clear session"),
    BotCommand(command="clone", description="Clone repo"),
    BotCommand(command="status", description="Git status"),
    BotCommand(command="commit", description="Commit changes"),
    BotCommand(command="push", description="Push to remote"),
    BotCommand(command="pull", description="Pull from remote"),
    BotCommand(command="merge", description="Merge branch"),
    BotCommand(command="branch", description="List/create branch"),
    BotCommand(command="actions", description="List workflow runs"),
    BotCommand(command="trigger", description="Trigger workflow"),
    BotCommand(command="logs", description="Get workflow logs"),
]

VIBE_BOT = BotSpec(
    name="vibe-bot",
    token_attr="VIBE_BOT_TOKEN",
    router_module="app.bots.vibe.handlers",
    commands=VIBE_BOT_COMMANDS,
)
