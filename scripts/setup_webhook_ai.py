import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from app.bots.ai.bot import AI_BOT
from app.bots.webhook_setup import setup_webhook_for_bot


async def setup():
    await setup_webhook_for_bot(AI_BOT)


if __name__ == "__main__":
    asyncio.run(setup())
