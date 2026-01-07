import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from app.bots.monitor.bot import MONITOR_BOT
from app.bots.webhook_setup import setup_webhook_for_bot


async def setup():
    await setup_webhook_for_bot(MONITOR_BOT)


if __name__ == "__main__":
    asyncio.run(setup())
