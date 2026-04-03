import asyncio
import random
from telegram.ext import Application

from src.config import POST_INTERVAL_HOURS, logger
from src.ai import generate_post
from src.memes import generate_meme
from src.bot import send_for_approval

post_count = 0


async def post_loop(app: Application):
    global post_count
    await asyncio.sleep(3)
    while True:
        try:
            is_meme = post_count % 3 == 2 or random.random() < 0.3
            post_count += 1

            if is_meme:
                logger.info("Generating meme...")
                post = generate_meme()
                if not post:
                    logger.info("Meme failed, falling back to news post")
                    post = generate_post()
            else:
                logger.info("Fetching latest tech news...")
                post = generate_post()

            await send_for_approval(app, post)
        except Exception as e:
            logger.error(f"Error generating post: {e}")

        logger.info(f"Next post in {POST_INTERVAL_HOURS} hours")
        await asyncio.sleep(POST_INTERVAL_HOURS * 3600)
