from aiogram.types import BotCommand

from app.bots.bot_spec import BotSpec



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
    BotCommand(command="export", description="导出自选"),
    BotCommand(command="scan", description="信号扫描"),
    BotCommand(command="sync", description="同步涨停"),
    BotCommand(command="history", description="个股历史"),
    BotCommand(command="chart", description="K线图表"),
    BotCommand(command="limitup", description="涨停报告"),
    BotCommand(command="daban", description="打板交易"),
    # Database commands
    BotCommand(command="dbcheck", description="数据库状态"),
    BotCommand(command="dbsync", description="同步历史数据"),
    # Trading simulator
    BotCommand(command="sim", description="模拟交易"),
    BotCommand(command="portfolio", description="持仓"),
    BotCommand(command="pnl", description="盈亏统计"),
    BotCommand(command="trades", description="交易历史"),
    # User management commands
    BotCommand(command="useradd", description="添加用户"),
    BotCommand(command="userdel", description="删除用户"),
    BotCommand(command="userlist", description="用户列表"),
    BotCommand(command="help", description="帮助"),
    # History commands
    BotCommand(command="forward_videos", description="转发历史视频"),
    BotCommand(command="save_history", description="保存聊天记录"),
    BotCommand(command="get_history", description="查询聊天记录"),
]

CRAWLER_BOT = BotSpec(
    name="crawler-bot",
    token_attr="CRAWLER_BOT_TOKEN",
    router_module="app.bots.crawler.handlers",
    commands=CRAWLER_BOT_COMMANDS,
)
