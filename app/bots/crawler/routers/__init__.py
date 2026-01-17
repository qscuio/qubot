"""
Crawler Bot Routers

This package contains modular routers for different features of the crawler bot.
Each router handles a specific domain of functionality.

Usage:
    from app.bots.crawler.routers import router

    # Register with dispatcher
    dp.include_router(router)
"""

from aiogram import Router

# Import all feature routers
from . import main
from . import crawler
from . import limit_up
from . import scanner
from . import sector
from . import user
from . import report
from . import watchlist
from . import simulator
from . import daban
from . import portfolio
from . import history
from . import ping

# Re-export common utilities for external use
from .common import (
    is_allowed,
    safe_answer,
    safe_edit_text,
    get_webapp_base,
    build_webapp_button,
    format_button_text,
    calculate_pagination,
    build_pagination_buttons,
    build_stock_list_ui,
    logger,
)

# Create the main router that aggregates all feature routers
router = Router(name="crawler_bot")

# Include all feature routers in order
# Order matters for callback query matching - more specific patterns should come first
router.include_router(main.router)
router.include_router(crawler.router)
router.include_router(limit_up.router)
router.include_router(scanner.router)
router.include_router(sector.router)
router.include_router(user.router)
router.include_router(report.router)
router.include_router(watchlist.router)
router.include_router(simulator.router)
router.include_router(daban.router)
router.include_router(portfolio.router)
router.include_router(history.router)
router.include_router(ping.router)

# Expose individual routers for more fine-grained control if needed
__all__ = [
    # Main aggregated router
    "router",

    # Individual feature routers
    "main",
    "crawler",
    "limit_up",
    "scanner",
    "sector",
    "user",
    "report",
    "watchlist",
    "simulator",
    "daban",
    "portfolio",
    "history",
    "ping",

    # Common utilities
    "is_allowed",
    "safe_answer",
    "safe_edit_text",
    "get_webapp_base",
    "build_webapp_button",
    "format_button_text",
    "calculate_pagination",
    "build_pagination_buttons",
    "build_stock_list_ui",
    "logger",
]
