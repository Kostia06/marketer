#!/usr/bin/env python3
import asyncio
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from src.config import TELEGRAM_TOKEN, logger
from src.bot import (
    start_command, generate_command, thread_command, linkedin_command,
    reply_command, meme_command, post_command, tone_command, button_handler,
)
from src.scheduler import post_loop


async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("generate", generate_command))
    app.add_handler(CommandHandler("thread", thread_command))
    app.add_handler(CommandHandler("linkedin", linkedin_command))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CommandHandler("meme", meme_command))
    app.add_handler(CommandHandler("post", post_command))
    app.add_handler(CommandHandler("tone", tone_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot started! Send /start in Telegram.")
    await post_loop(app)


if __name__ == "__main__":
    asyncio.run(main())
