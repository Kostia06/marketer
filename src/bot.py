import os
import time
import subprocess
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.ext import Application, ContextTypes

BOT_START_TIME = time.time()
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

from src.config import (
    TELEGRAM_CHAT_ID,
    MIN_DELAY_MINUTES,
    MAX_DELAY_MINUTES,
    POST_INTERVAL_HOURS,
    logger,
)
from src.ai import generate_post, generate_thread, generate_linkedin_post
from src.reply_bot import fetch_tweet_text, generate_reply
from src.platforms.x import post_to_x, delete_from_x
from src.platforms.linkedin import post_to_linkedin, delete_from_linkedin
from src.history import save_post

# ── State ──
pending_posts: dict[int, dict] = {}
pending_threads: dict[int, dict] = {}
pending_replies: dict[int, dict] = {}
scheduled_tasks: dict[int, asyncio.Task] = {}
posted_results: dict[int, dict] = {}
panel_msg_id: int | None = None
is_paused: bool = False


# ── Helpers ──
async def delete_msg(bot, chat_id, msg_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass


async def auto_delete_after(bot, chat_id, msg_id, seconds=10):
    await asyncio.sleep(seconds)
    await delete_msg(bot, chat_id, msg_id)


async def flash(bot, text, seconds=10):
    msg = await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown")
    asyncio.create_task(auto_delete_after(bot, TELEGRAM_CHAT_ID, msg.message_id, seconds))


# ── Control Panel ──
def build_panel_text():
    from src.history import load_history
    uptime_sec = int(time.time() - BOT_START_TIME)
    hours, minutes = divmod(uptime_sec, 3600)[0], divmod(uptime_sec % 3600, 60)[0]
    status = "Paused" if is_paused else "Running"
    post_count = len(load_history())
    pending = len(pending_posts) + len(pending_threads) + len(pending_replies)
    try:
        version = subprocess.check_output(["git", "log", "-1", "--format=%h"], text=True).strip()
    except Exception:
        version = "?"
    return (
        f"*Marketer Bot*\n\n"
        f"Status: *{status}*\n"
        f"Uptime: {hours}h {minutes}m\n"
        f"Version: `{version}`\n"
        f"Posts published: {post_count}\n"
        f"Pending: {pending}"
    )


def build_panel_keyboard():
    pause_btn = InlineKeyboardButton("Resume" if is_paused else "Pause", callback_data="toggle_pause")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Generate", callback_data="cmd_generate"),
            InlineKeyboardButton("Thread", callback_data="cmd_thread"),
            InlineKeyboardButton("Meme", callback_data="cmd_meme"),
        ],
        [
            InlineKeyboardButton("LinkedIn", callback_data="cmd_linkedin"),
            pause_btn,
            InlineKeyboardButton("Clear", callback_data="cmd_clear"),
        ],
        [
            InlineKeyboardButton("History", callback_data="cmd_history"),
            InlineKeyboardButton("Queue", callback_data="cmd_queue"),
            InlineKeyboardButton("Ping", callback_data="cmd_ping"),
        ],
    ])


async def show_panel(bot):
    global panel_msg_id
    if panel_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=TELEGRAM_CHAT_ID,
                message_id=panel_msg_id,
                text=build_panel_text(),
                parse_mode="Markdown",
                reply_markup=build_panel_keyboard(),
            )
            return
        except Exception:
            pass

    msg = await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=build_panel_text(),
        parse_mode="Markdown",
        reply_markup=build_panel_keyboard(),
    )
    panel_msg_id = msg.message_id
    try:
        await bot.pin_chat_message(chat_id=TELEGRAM_CHAT_ID, message_id=msg.message_id, disable_notification=True)
    except Exception:
        pass


# ── Approval Flow ──
async def send_for_approval(app: Application, post: dict):
    global panel_msg_id
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
        f"*New Post*\n\n"
        f"{text}\n\n"
        f"{source_line}"
        f"Delay: *{delay}m*"
    )

    if panel_msg_id:
        await delete_msg(app.bot, TELEGRAM_CHAT_ID, panel_msg_id)
        panel_msg_id = None

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as photo:
            msg = await app.bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID, photo=photo,
                caption=caption, parse_mode="Markdown", reply_markup=reply_markup,
            )
    else:
        msg = await app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=caption,
            parse_mode="Markdown", reply_markup=reply_markup, link_preview_options=NO_PREVIEW,
        )

    pending_posts[msg.message_id] = post
    logger.info(f"Sent post for approval (message_id={msg.message_id})")


async def publish_post(text, image_path, message_id, context, source_url=""):
    clean_text = text.replace("\n", " ").strip()
    x_text = f"{clean_text} {source_url}".strip() if source_url else clean_text
    li_text = f"{clean_text}\n\n{source_url}".strip() if source_url else clean_text
    x_ok, x_id = post_to_x(x_text, image_path)
    li_ok, li_urn = post_to_linkedin(li_text, image_path)

    results = ["X: posted" if x_ok else "X: failed", "LinkedIn: posted" if li_ok else "LinkedIn: failed"]
    posted_results[message_id] = {"x_id": x_id, "li_urn": li_urn, "text": text}
    if x_ok or li_ok:
        save_post(text, source_url)

    await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)

    short_text = text[:60] + "..." if len(text) > 60 else text
    delete_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Undo", callback_data=f"delete|{message_id}")]
    ])
    msg = await context.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"*{', '.join(results)}*\n_{short_text}_",
        parse_mode="Markdown", link_preview_options=NO_PREVIEW, reply_markup=delete_keyboard,
    )
    asyncio.create_task(auto_delete_after(context.bot, TELEGRAM_CHAT_ID, msg.message_id, 30))
    asyncio.create_task(restore_panel_delayed(context.bot, 2))

    if image_path and os.path.exists(image_path):
        os.unlink(image_path)


async def restore_panel_delayed(bot, seconds):
    await asyncio.sleep(seconds)
    await show_panel(bot)


async def delayed_publish(delay, text, image_path, message_id, context, source_url=""):
    await asyncio.sleep(delay * 60)
    await publish_post(text, image_path, message_id, context, source_url)
    scheduled_tasks.pop(message_id, None)


# ── Button Handler ──
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    message_id = query.message.message_id

    # ── Panel commands ──
    if action == "cmd_generate":
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        global panel_msg_id
        panel_msg_id = None
        await flash(context.bot, "_Generating post..._")
        post = generate_post()
        await send_for_approval(context.application, post)
        return

    if action == "cmd_thread":
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        panel_msg_id = None
        await flash(context.bot, "_Generating thread..._")
        thread = generate_thread()
        tweets = thread["tweets"]
        source_url = thread.get("source_url", "")
        preview = "\n\n".join(f"*{i+1}.* {t}" for i, t in enumerate(tweets))
        if source_url:
            preview += f"\n\nSource: {source_url}"
        keyboard = [
            [InlineKeyboardButton("Post Thread", callback_data="postthread"),
             InlineKeyboardButton("Rewrite", callback_data="rewritethread")],
            [InlineKeyboardButton("Back", callback_data="back_to_panel")],
        ]
        msg = await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=f"*Thread ({len(tweets)} tweets):*\n\n{preview}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), link_preview_options=NO_PREVIEW,
        )
        pending_threads[msg.message_id] = thread
        return

    if action == "cmd_meme":
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        panel_msg_id = None
        await flash(context.bot, "_Generating meme..._")
        from src.memes import generate_meme
        post = generate_meme()
        if post:
            await send_for_approval(context.application, post)
        else:
            await flash(context.bot, "Meme failed. Try again.")
            await show_panel(context.bot)
        return

    if action == "cmd_linkedin":
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        panel_msg_id = None
        await flash(context.bot, "_Generating LinkedIn post..._")
        post = generate_linkedin_post()
        source_url = post.get("source_url", "")
        preview = post["text"]
        if source_url:
            preview += f"\n\nSource: {source_url}"
        keyboard = [
            [InlineKeyboardButton("Post", callback_data="postlinkedin"),
             InlineKeyboardButton("Rewrite", callback_data="rewritelinkedin")],
            [InlineKeyboardButton("Back", callback_data="back_to_panel")],
        ]
        msg = await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=f"*LinkedIn:*\n\n{preview}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), link_preview_options=NO_PREVIEW,
        )
        pending_posts[msg.message_id] = {"text": post["text"], "source_url": source_url, "image_path": None, "linkedin_only": True}
        return

    if action == "toggle_pause":
        global is_paused
        is_paused = not is_paused
        logger.info(f"Bot {'paused' if is_paused else 'resumed'}")
        await show_panel(context.bot)
        return

    if action == "cmd_clear":
        for i in range(1, 100):
            await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id - i)
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        panel_msg_id = None
        pending_posts.clear()
        pending_threads.clear()
        pending_replies.clear()
        await show_panel(context.bot)
        return

    if action == "cmd_history":
        from src.history import load_history
        history = load_history()
        if not history:
            await flash(context.bot, "No posts yet.")
            return
        recent = history[-10:][::-1]
        lines = [f"*{i}.* {h['text'][:60]}..." if len(h['text']) > 60 else f"*{i}.* {h['text']}" for i, h in enumerate(recent, 1)]
        keyboard = [[InlineKeyboardButton("Back", callback_data="back_to_panel")]]
        await query.edit_message_text(
            f"*Last {len(recent)} posts:*\n\n" + "\n\n".join(lines),
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if action == "cmd_queue":
        items = []
        for mid, post in pending_posts.items():
            txt = post["text"][:40] + "..." if len(post["text"]) > 40 else post["text"]
            st = "scheduled" if mid in scheduled_tasks else "pending"
            items.append(f"- _{txt}_ ({st})")
        for mid in pending_threads:
            items.append("- Thread (pending)")
        for mid, r in pending_replies.items():
            items.append(f"- Reply to @{r['tweet']['author']}")
        keyboard = [[InlineKeyboardButton("Back", callback_data="back_to_panel")]]
        await query.edit_message_text(
            f"*Queue ({len(items)}):*\n\n" + ("\n".join(items) if items else "Empty"),
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if action == "cmd_ping":
        uptime_sec = int(time.time() - BOT_START_TIME)
        h, r = divmod(uptime_sec, 3600)
        m, s = divmod(r, 60)
        from src.history import load_history
        try:
            ver = subprocess.check_output(["git", "log", "-1", "--format=%h %s"], text=True).strip()
            updated = subprocess.check_output(["git", "log", "-1", "--format=%cr"], text=True).strip()
        except Exception:
            ver, updated = "?", "?"
        keyboard = [[InlineKeyboardButton("Back", callback_data="back_to_panel")]]
        await query.edit_message_text(
            f"*pong.*\n\n"
            f"uptime: {h}h {m}m {s}s\n"
            f"version: `{ver}`\n"
            f"updated: {updated}\n"
            f"published: {len(load_history())}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if action == "back_to_panel":
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        panel_msg_id = None
        await show_panel(context.bot)
        return

    # ── Delete ──
    if action.startswith("delete"):
        ref_id = int(action.split("|")[1])
        result = posted_results.pop(ref_id, None)
        statuses = []
        if result and result.get("x_id"):
            ok = delete_from_x(result["x_id"])
            statuses.append("X: deleted" if ok else "X: failed")
        if result and result.get("li_urn"):
            ok = delete_from_linkedin(result["li_urn"])
            statuses.append("LinkedIn: deleted" if ok else "LinkedIn: failed")
        await query.edit_message_text(f"*{', '.join(statuses or ['Nothing to delete'])}*", parse_mode="Markdown")
        asyncio.create_task(auto_delete_after(context.bot, TELEGRAM_CHAT_ID, message_id, 10))
        return

    if action == "cancel":
        task = scheduled_tasks.pop(message_id, None)
        if task:
            task.cancel()
        post = pending_posts.pop(message_id, None)
        if post and post.get("image_path") and os.path.exists(post["image_path"]):
            os.unlink(post["image_path"])
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        await flash(context.bot, "Cancelled.", 5)
        await show_panel(context.bot)
        return

    # ── Thread ──
    if action == "postthread":
        thread = pending_threads.pop(message_id, None)
        if not thread:
            return
        await query.edit_message_text("*Posting thread...*", parse_mode="Markdown")
        tweets = thread["tweets"]
        source_url = thread.get("source_url", "")
        first_text = f"{tweets[0]} {source_url}".strip() if source_url else tweets[0]
        x_ok, first_id = post_to_x(first_text)
        prev_id = first_id
        for tweet in tweets[1:]:
            if prev_id:
                from src.platforms.x import get_client
                try:
                    resp = get_client().create_tweet(text=tweet, in_reply_to_tweet_id=prev_id)
                    prev_id = resp.data["id"]
                except Exception as e:
                    logger.error(f"Thread tweet failed: {e}")
                    break
        li_text = "\n\n".join(tweets)
        if source_url:
            li_text += f"\n\n{source_url}"
        li_ok, _ = post_to_linkedin(li_text)
        save_post(tweets[0], source_url)
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        await flash(context.bot, f"*Thread published.* X: {'posted' if x_ok else 'failed'}, LinkedIn: {'posted' if li_ok else 'failed'}", 15)
        await show_panel(context.bot)
        return

    if action == "rewritethread":
        pending_threads.pop(message_id, None)
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        await flash(context.bot, "_Rewriting thread..._")
        thread = generate_thread()
        tweets = thread["tweets"]
        preview = "\n\n".join(f"*{i+1}.* {t}" for i, t in enumerate(tweets))
        keyboard = [
            [InlineKeyboardButton("Post Thread", callback_data="postthread"),
             InlineKeyboardButton("Rewrite", callback_data="rewritethread")],
            [InlineKeyboardButton("Back", callback_data="back_to_panel")],
        ]
        msg = await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=f"*Thread ({len(tweets)} tweets):*\n\n{preview}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), link_preview_options=NO_PREVIEW,
        )
        pending_threads[msg.message_id] = thread
        return

    # ── Reply ──
    if action == "sendreply":
        reply_data = pending_replies.pop(message_id, None)
        if not reply_data:
            return
        tweet = reply_data["tweet"]
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        try:
            from src.platforms.x import get_client
            get_client().create_tweet(text=reply_data["reply_text"], in_reply_to_tweet_id=tweet["tweet_id"])
            await flash(context.bot, f"*Replied to @{tweet['author']}*", 15)
        except Exception as e:
            await flash(context.bot, f"*Reply failed:* {e}", 15)
        await show_panel(context.bot)
        return

    if action == "rewritereply":
        reply_data = pending_replies.pop(message_id, None)
        if not reply_data:
            return
        tweet = reply_data["tweet"]
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        new_reply = generate_reply(tweet["text"], tweet["author"])
        keyboard = [
            [InlineKeyboardButton("Reply", callback_data="sendreply"),
             InlineKeyboardButton("Rewrite", callback_data="rewritereply")],
            [InlineKeyboardButton("Back", callback_data="back_to_panel")],
        ]
        msg = await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"*Reply to @{tweet['author']}:*\n_{tweet['text'][:150]}_\n\n{new_reply}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), link_preview_options=NO_PREVIEW,
        )
        pending_replies[msg.message_id] = {"reply_text": new_reply, "tweet": tweet}
        return

    # ── LinkedIn ──
    if action == "postlinkedin":
        post = pending_posts.pop(message_id, None)
        if not post:
            return
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        li_text = f"{post['text']}\n\n{post.get('source_url', '')}".strip()
        li_ok, li_urn = post_to_linkedin(li_text)
        save_post(post["text"], post.get("source_url", ""))
        posted_results[message_id] = {"x_id": None, "li_urn": li_urn, "text": post["text"]}
        await flash(context.bot, f"*LinkedIn: {'posted' if li_ok else 'failed'}*", 15)
        await show_panel(context.bot)
        return

    if action == "rewritelinkedin":
        pending_posts.pop(message_id, None)
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        await flash(context.bot, "_Rewriting LinkedIn post..._")
        post = generate_linkedin_post()
        source_url = post.get("source_url", "")
        preview = post["text"]
        if source_url:
            preview += f"\n\nSource: {source_url}"
        keyboard = [
            [InlineKeyboardButton("Post", callback_data="postlinkedin"),
             InlineKeyboardButton("Rewrite", callback_data="rewritelinkedin")],
            [InlineKeyboardButton("Back", callback_data="back_to_panel")],
        ]
        msg = await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=f"*LinkedIn:*\n\n{preview}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), link_preview_options=NO_PREVIEW,
        )
        pending_posts[msg.message_id] = {"text": post["text"], "source_url": source_url, "image_path": None, "linkedin_only": True}
        return

    # ── Standard post ──
    post = pending_posts.get(message_id)
    if not post:
        return

    text = post["text"]
    image_path = post.get("image_path")
    source_url = post.get("source_url", "")

    if action.startswith("approve"):
        delay = int(action.split("|")[1])
        pending_posts.pop(message_id, None)
        cancel_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel")]])
        if query.message.photo:
            await query.edit_message_caption(
                caption=f"*Posting in {delay}m...*\n\n{text}", parse_mode="Markdown", reply_markup=cancel_keyboard)
        else:
            await query.edit_message_text(
                f"*Posting in {delay}m...*\n\n{text}", parse_mode="Markdown", reply_markup=cancel_keyboard)
        pending_posts[message_id] = post
        task = asyncio.create_task(delayed_publish(delay, text, image_path, message_id, context, source_url))
        scheduled_tasks[message_id] = task

    elif action == "postnow":
        pending_posts.pop(message_id, None)
        await publish_post(text, image_path, message_id, context, source_url)

    elif action == "reject":
        pending_posts.pop(message_id, None)
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)
        await flash(context.bot, "Rejected.", 5)
        await show_panel(context.bot)

    elif action == "rewrite":
        pending_posts.pop(message_id, None)
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)
        post = generate_post()
        await send_for_approval(context.application, post)


# ── Commands (minimal — panel handles most) ──
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_msg(context.bot, TELEGRAM_CHAT_ID, update.message.message_id)
    await show_panel(context.bot)


async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.replace("/reply", "", 1).strip()
    await delete_msg(context.bot, TELEGRAM_CHAT_ID, update.message.message_id)
    if not url or "status/" not in url:
        await flash(context.bot, "Usage: /reply <tweet\\_url>")
        return
    await flash(context.bot, "_Crafting reply..._")
    tweet = fetch_tweet_text(url)
    if not tweet:
        await flash(context.bot, "Couldn't fetch that tweet.")
        return
    reply_text = generate_reply(tweet["text"], tweet["author"])
    keyboard = [
        [InlineKeyboardButton("Reply", callback_data="sendreply"),
         InlineKeyboardButton("Rewrite", callback_data="rewritereply")],
        [InlineKeyboardButton("Back", callback_data="back_to_panel")],
    ]
    if panel_msg_id:
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, panel_msg_id)
    msg = await context.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"*Reply to @{tweet['author']}:*\n_{tweet['text'][:150]}_\n\n{reply_text}",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), link_preview_options=NO_PREVIEW,
    )
    pending_replies[msg.message_id] = {"reply_text": reply_text, "tweet": tweet}


async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.replace("/post", "", 1).strip()
    await delete_msg(context.bot, TELEGRAM_CHAT_ID, update.message.message_id)
    if not user_text:
        await flash(context.bot, "Usage: /post your text here")
        return
    post = {"text": user_text, "source_url": "", "image_path": None}
    await send_for_approval(context.application, post)
