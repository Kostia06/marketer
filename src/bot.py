import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.ext import Application, ContextTypes

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

from src.config import (
    TELEGRAM_CHAT_ID,
    MIN_DELAY_MINUTES,
    MAX_DELAY_MINUTES,
    POST_INTERVAL_HOURS,
    logger,
)
from src.ai import generate_post
from src.platforms.x import post_to_x, delete_from_x
from src.platforms.linkedin import post_to_linkedin, delete_from_linkedin

pending_posts: dict[int, dict] = {}
scheduled_tasks: dict[int, asyncio.Task] = {}
posted_results: dict[int, dict] = {}


async def send_for_approval(app: Application, post: dict):
    delay = random.randint(MIN_DELAY_MINUTES, MAX_DELAY_MINUTES)
    text = post["text"]
    image_path = post.get("image_path")
    source_url = post.get("source_url", "")

    keyboard = [
        [
            InlineKeyboardButton("Approve", callback_data=f"approve|{delay}"),
            InlineKeyboardButton("Post Now", callback_data="postnow"),
        ],
        [
            InlineKeyboardButton("Reject", callback_data="reject"),
            InlineKeyboardButton("Rewrite", callback_data="rewrite"),
        ],
    ]
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
            link_preview_options=NO_PREVIEW,
        )

    pending_posts[msg.message_id] = post
    logger.info(f"Sent post for approval (message_id={msg.message_id})")


async def publish_post(text, image_path, message_id, context, source_url=""):
    """Publish to X and LinkedIn, then show result with delete button."""
    publish_text = f"{text}\n\n{source_url}" if source_url else text
    x_ok, x_id = post_to_x(publish_text, image_path)
    li_ok, li_urn = post_to_linkedin(publish_text, image_path)

    results = [
        "X: posted" if x_ok else "X: failed",
        "LinkedIn: posted" if li_ok else "LinkedIn: failed",
    ]

    posted_results[message_id] = {"x_id": x_id, "li_urn": li_urn, "text": text}

    delete_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Delete Posts", callback_data=f"delete|{message_id}")]
    ])

    await context.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"*Post published!*\n" + "\n".join(results) + f"\n\n_{text}_",
        parse_mode="Markdown",
        link_preview_options=NO_PREVIEW,
        reply_markup=delete_keyboard,
    )

    if image_path and os.path.exists(image_path):
        os.unlink(image_path)


async def delayed_publish(delay, text, image_path, message_id, context, source_url=""):
    """Wait then publish. Can be cancelled."""
    await asyncio.sleep(delay * 60)
    await publish_post(text, image_path, message_id, context, source_url)
    scheduled_tasks.pop(message_id, None)


def edit_msg(query, text, parse_mode="Markdown"):
    if query.message.photo:
        return query.edit_message_caption(caption=text, parse_mode=parse_mode)
    return query.edit_message_text(text, parse_mode=parse_mode)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data
    message_id = query.message.message_id

    if action.startswith("delete"):
        ref_id = int(action.split("|")[1])
        result = posted_results.pop(ref_id, None)
        statuses = []
        if result and result.get("x_id"):
            ok = delete_from_x(result["x_id"])
            statuses.append("X: deleted" if ok else "X: failed to delete")
        else:
            statuses.append("X: nothing to delete")
        if result and result.get("li_urn"):
            ok = delete_from_linkedin(result["li_urn"])
            statuses.append("LinkedIn: deleted" if ok else "LinkedIn: failed to delete")
        else:
            statuses.append("LinkedIn: nothing to delete")
        await query.edit_message_text(
            "*Delete results:*\n" + "\n".join(statuses),
            parse_mode="Markdown",
        )
        return

    if action == "cancel":
        task = scheduled_tasks.pop(message_id, None)
        if task:
            task.cancel()
        post = pending_posts.pop(message_id, None)
        if post and post.get("image_path") and os.path.exists(post["image_path"]):
            os.unlink(post["image_path"])
        await edit_msg(query, "*Cancelled.* Post will not be published.")
        return

    post = pending_posts.get(message_id)
    if not post:
        await query.edit_message_text("This post has already been handled.")
        return

    text = post["text"]
    image_path = post.get("image_path")
    source_url = post.get("source_url", "")

    if action.startswith("approve"):
        delay = int(action.split("|")[1])
        pending_posts.pop(message_id, None)

        cancel_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Cancel", callback_data="cancel")]
        ])

        if query.message.photo:
            await query.edit_message_caption(
                caption=f"*Approved!* Posting in {delay} minutes...\n\n{text}",
                parse_mode="Markdown",
                reply_markup=cancel_keyboard,
            )
        else:
            await query.edit_message_text(
                f"*Approved!* Posting in {delay} minutes...\n\n{text}",
                parse_mode="Markdown",
                reply_markup=cancel_keyboard,
            )

        pending_posts[message_id] = post
        task = asyncio.create_task(
            delayed_publish(delay, text, image_path, message_id, context, source_url)
        )
        scheduled_tasks[message_id] = task

    elif action == "postnow":
        pending_posts.pop(message_id, None)
        await edit_msg(query, f"*Posting now...*\n\n{text}")
        await publish_post(text, image_path, message_id, context, source_url)

    elif action == "reject":
        pending_posts.pop(message_id, None)
        await edit_msg(query, "*Post rejected.* Next post at next interval.")
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

    elif action == "rewrite":
        pending_posts.pop(message_id, None)
        await edit_msg(query, "*Rewriting post, one moment...*")
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)
        new_post = generate_post()
        await send_for_approval(context.application, new_post)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Tech Post Bot*\n\n"
        f"Posts every *{POST_INTERVAL_HOURS}h* with your approval.\n\n"
        "Commands:\n"
        "/generate — AI post from latest news\n"
        "/post your text here — preview your own post\n"
        "/tone — refresh style guide\n\n"
        "Buttons:\n"
        "*Approve* — post after random delay\n"
        "*Post Now* — post immediately\n"
        "*Reject* — skip\n"
        "*Rewrite* — regenerate\n"
        "*Cancel* — stop a scheduled post\n"
        "*Delete Posts* — remove after publishing",
        parse_mode="Markdown",
    )


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching latest tech news...")
    post = generate_post()
    await send_for_approval(context.application, post)


async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.replace("/post", "", 1).strip()
    if not user_text:
        await update.message.reply_text("Usage: `/post your text here`", parse_mode="Markdown")
        return
    post = {"text": user_text, "source_url": "", "image_path": None}
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
