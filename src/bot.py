import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

from src.config import (
    TELEGRAM_CHAT_ID,
    MIN_DELAY_MINUTES,
    MAX_DELAY_MINUTES,
    POST_INTERVAL_HOURS,
    logger,
)
from src.ai import generate_post
from src.platforms.x import post_to_x
from src.platforms.linkedin import post_to_linkedin

pending_posts: dict[int, dict] = {}


async def send_for_approval(app: Application, post: dict):
    delay = random.randint(MIN_DELAY_MINUTES, MAX_DELAY_MINUTES)
    text = post["text"]
    image_path = post.get("image_path")
    source_url = post.get("source_url", "")

    keyboard = [[
        InlineKeyboardButton("Approve", callback_data=f"approve|{delay}"),
        InlineKeyboardButton("Reject", callback_data="reject"),
        InlineKeyboardButton("Rewrite", callback_data="rewrite"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    source_line = f"Source: {source_url}\n" if source_url else ""
    caption = (
        f"*New Tech Post Ready for Approval*\n\n"
        f"{text}\n\n"
        f"{source_line}"
        f"If approved, will post in *{delay} minutes*"
    )

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as photo:
            msg = await app.bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=photo,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
    else:
        msg = await app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    pending_posts[msg.message_id] = post
    logger.info(f"Sent post for approval (message_id={msg.message_id})")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    message_id = query.message.message_id
    post = pending_posts.get(message_id)

    if not post:
        await query.edit_message_text("This post has already been handled.")
        return

    action = query.data
    text = post["text"]
    image_path = post.get("image_path")

    if action.startswith("approve"):
        delay = int(action.split("|")[1])
        pending_posts.pop(message_id, None)

        await query.edit_message_caption(
            caption=f"*Approved!* Posting in {delay} minutes...\n\n{text}",
            parse_mode="Markdown",
        ) if query.message.photo else await query.edit_message_text(
            f"*Approved!* Posting in {delay} minutes...\n\n{text}",
            parse_mode="Markdown",
        )

        await asyncio.sleep(delay * 60)

        x_ok = post_to_x(text, image_path)
        li_ok = post_to_linkedin(text)

        results = [
            "X (Twitter): posted" if x_ok else "X (Twitter): failed",
            "LinkedIn: posted" if li_ok else "LinkedIn: failed",
        ]
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="*Post published!*\n" + "\n".join(results),
            parse_mode="Markdown",
        )

        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

    elif action == "reject":
        pending_posts.pop(message_id, None)
        if query.message.photo:
            await query.edit_message_caption(caption="*Post rejected.* Next post at next interval.")
        else:
            await query.edit_message_text("*Post rejected.* Next post at next interval.")
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

    elif action == "rewrite":
        pending_posts.pop(message_id, None)
        if query.message.photo:
            await query.edit_message_caption(caption="*Rewriting post, one moment...*")
        else:
            await query.edit_message_text("*Rewriting post, one moment...*")
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)
        new_post = generate_post()
        await send_for_approval(context.application, new_post)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Tech Post Bot is running!*\n\n"
        f"I fetch the latest tech news every *{POST_INTERVAL_HOURS} hours*, "
        f"write a post about it, and ask for your approval before posting to X and LinkedIn.\n\n"
        "Buttons:\n"
        "*Approve* — schedules the post at a random delay\n"
        "*Reject* — skips it, waits for next interval\n"
        "*Rewrite* — generates a brand new post right now",
        parse_mode="Markdown",
    )


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching latest tech news...")
    post = generate_post()
    await send_for_approval(context.application, post)


async def tone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Analyzing top tech creators... this takes a minute.")
    from src.toner import run_analysis
    guide = run_analysis()
    patterns = len(guide.get("patterns", []))
    hooks = len(guide.get("hooks", []))
    rules = len(guide.get("tone_rules", []))
    await update.message.reply_text(
        f"*Style guide updated!*\n\n"
        f"Learned {patterns} patterns, {hooks} hooks, {rules} tone rules\n"
        f"Future posts will use these insights.",
        parse_mode="Markdown",
    )
