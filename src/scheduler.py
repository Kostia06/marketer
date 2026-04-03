import asyncio
from telegram.ext import Application

from src.config import POST_INTERVAL_HOURS, logger
from src.ai import generate_post
from src.bot import send_for_approval


async def post_loop(app: Application):
    await asyncio.sleep(3)
    while True:
        try:
            logger.info("Fetching latest tech news...")
            post = generate_post()
            await send_for_approval(app, post)
        except Exception as e:
            logger.error(f"Error generating post: {e}")

        logger.info(f"Next post in {POST_INTERVAL_HOURS} hours")
        await asyncio.sleep(POST_INTERVAL_HOURS * 3600)
