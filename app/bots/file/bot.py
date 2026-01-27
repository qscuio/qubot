from aiogram.types import BotCommand

from app.bots.bot_spec import BotSpec

FILE_BOT_COMMANDS = [
    BotCommand(command="start", description="主菜单"),
    BotCommand(command="help", description="帮助"),
    BotCommand(command="fv", description="转发历史视频"),
    BotCommand(command="fv_target", description="设置视频转发目标"),
]

FILE_BOT = BotSpec(
    name="file-bot",
    token_attr="FILE_BOT_TOKEN",
    router_module="app.bots.file.handlers",
    commands=FILE_BOT_COMMANDS,
)
