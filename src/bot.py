import os
import time
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
from src.reply_bot import fetch_tweet_text, generate_reply, extract_tweet_id
from src.platforms.x import post_to_x, delete_from_x
from src.platforms.linkedin import post_to_linkedin, delete_from_linkedin
from src.history import save_post

pending_posts: dict[int, dict] = {}
pending_threads: dict[int, dict] = {}
pending_replies: dict[int, dict] = {}
scheduled_tasks: dict[int, asyncio.Task] = {}
posted_results: dict[int, dict] = {}
last_approval_msg_id: int | None = None
bot_message_ids: list[int] = []


async def delete_msg(bot, chat_id, msg_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass


def track_msg(msg_id):
    bot_message_ids.append(msg_id)
    if len(bot_message_ids) > 100:
        bot_message_ids.pop(0)


async def auto_delete_after(bot, chat_id, msg_id, seconds=30):
    await asyncio.sleep(seconds)
    await delete_msg(bot, chat_id, msg_id)


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

    global last_approval_msg_id
    if last_approval_msg_id:
        await delete_msg(app.bot, TELEGRAM_CHAT_ID, last_approval_msg_id)

    pending_posts[msg.message_id] = post
    last_approval_msg_id = msg.message_id
    track_msg(msg.message_id)

    try:
        await app.bot.pin_chat_message(chat_id=TELEGRAM_CHAT_ID, message_id=msg.message_id, disable_notification=True)
    except Exception:
        pass

    logger.info(f"Sent post for approval (message_id={msg.message_id})")


async def publish_post(text, image_path, message_id, context, source_url=""):
    """Publish to X and LinkedIn, then show result with delete button."""
    clean_text = text.replace("\n", " ").strip()
    x_text = f"{clean_text} {source_url}".strip() if source_url else clean_text
    li_text = f"{clean_text}\n\n{source_url}".strip() if source_url else clean_text
    x_ok, x_id = post_to_x(x_text, image_path)
    li_ok, li_urn = post_to_linkedin(li_text, image_path)

    results = [
        "X: posted" if x_ok else "X: failed",
        "LinkedIn: posted" if li_ok else "LinkedIn: failed",
    ]

    posted_results[message_id] = {"x_id": x_id, "li_urn": li_urn, "text": text}
    if x_ok or li_ok:
        save_post(text, source_url)

    await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)

    delete_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Delete Posts", callback_data=f"delete|{message_id}")]
    ])

    short_text = text[:80] + "..." if len(text) > 80 else text
    confirm_msg = await context.bot.send_message(  # noqa
        chat_id=TELEGRAM_CHAT_ID,
        text=f"*Published:* {', '.join(results)}\n_{short_text}_",
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
            statuses.append("X: deleted" if ok else "X: failed")
        else:
            statuses.append("X: nothing to delete")
        if result and result.get("li_urn"):
            ok = delete_from_linkedin(result["li_urn"])
            statuses.append("LinkedIn: deleted" if ok else "LinkedIn: failed")
        else:
            statuses.append("LinkedIn: nothing to delete")
        await query.edit_message_text(f"*Deleted:* {', '.join(statuses)}", parse_mode="Markdown")
        asyncio.create_task(auto_delete_after(context.bot, TELEGRAM_CHAT_ID, message_id, 15))
        return

    if action == "cancel":
        task = scheduled_tasks.pop(message_id, None)
        if task:
            task.cancel()
        post = pending_posts.pop(message_id, None)
        if post and post.get("image_path") and os.path.exists(post["image_path"]):
            os.unlink(post["image_path"])
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        tmp = await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Cancelled.")
        asyncio.create_task(auto_delete_after(context.bot, TELEGRAM_CHAT_ID, tmp.message_id, 10))
        return

    # ── Thread handlers ──
    if action == "postthread":
        thread = pending_threads.pop(message_id, None)
        if not thread:
            await query.edit_message_text("Thread already handled.")
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
        li_ok, li_urn = post_to_linkedin(li_text)
        save_post(tweets[0], source_url)
        results = ["X: posted" if x_ok else "X: failed", "LinkedIn: posted" if li_ok else "LinkedIn: failed"]
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="*Thread published!*\n" + "\n".join(results),
            parse_mode="Markdown",
            link_preview_options=NO_PREVIEW,
        )
        return

    if action == "rewritethread":
        pending_threads.pop(message_id, None)
        await query.edit_message_text("*Rewriting thread...*", parse_mode="Markdown")
        thread = generate_thread()
        tweets = thread["tweets"]
        preview = "\n\n".join(f"*{i+1}.* {t}" for i, t in enumerate(tweets))
        source_url = thread.get("source_url", "")
        if source_url:
            preview += f"\n\nSource: {source_url}"
        keyboard = [
            [InlineKeyboardButton("Post Thread", callback_data="postthread"),
             InlineKeyboardButton("Rewrite", callback_data="rewritethread")],
            [InlineKeyboardButton("Reject", callback_data="reject")],
        ]
        msg = await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"*Thread Preview ({len(tweets)} tweets):*\n\n{preview}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
            link_preview_options=NO_PREVIEW,
        )
        pending_threads[msg.message_id] = thread
        return

    # ── Reply handlers ──
    if action == "sendreply":
        reply_data = pending_replies.pop(message_id, None)
        if not reply_data:
            await query.edit_message_text("Reply already handled.")
            return
        tweet = reply_data["tweet"]
        reply_text = reply_data["reply_text"]
        await query.edit_message_text("*Sending reply...*", parse_mode="Markdown")
        try:
            from src.platforms.x import get_client
            resp = get_client().create_tweet(text=reply_text, in_reply_to_tweet_id=tweet["tweet_id"])
            await context.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=f"*Replied to @{tweet['author']}!*\n\n{reply_text}",
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW,
            )
        except Exception as e:
            logger.error(f"Reply failed: {e}")
            await context.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID, text=f"*Reply failed:* {e}", parse_mode="Markdown",
            )
        return

    if action == "rewritereply":
        reply_data = pending_replies.pop(message_id, None)
        if not reply_data:
            await query.edit_message_text("Reply already handled.")
            return
        tweet = reply_data["tweet"]
        await query.edit_message_text("*Rewriting reply...*", parse_mode="Markdown")
        new_reply = generate_reply(tweet["text"], tweet["author"])
        keyboard = [
            [InlineKeyboardButton("Reply Now", callback_data="sendreply"),
             InlineKeyboardButton("Rewrite", callback_data="rewritereply")],
            [InlineKeyboardButton("Reject", callback_data="reject")],
        ]
        msg = await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"*Replying to @{tweet['author']}:*\n_{tweet['text'][:200]}_\n\n*Your reply:*\n{new_reply}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
            link_preview_options=NO_PREVIEW,
        )
        pending_replies[msg.message_id] = {"reply_text": new_reply, "tweet": tweet}
        return

    # ── LinkedIn-only handler ──
    if action == "postlinkedin":
        post = pending_posts.pop(message_id, None)
        if not post:
            await query.edit_message_text("Post already handled.")
            return
        await query.edit_message_text("*Posting to LinkedIn...*", parse_mode="Markdown")
        li_text = f"{post['text']}\n\n{post['source_url']}".strip()
        li_ok, li_urn = post_to_linkedin(li_text)
        save_post(post["text"], post.get("source_url", ""))
        posted_results[message_id] = {"x_id": None, "li_urn": li_urn, "text": post["text"]}
        delete_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Delete Posts", callback_data=f"delete|{message_id}")]
        ])
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"*LinkedIn: {'posted' if li_ok else 'failed'}*",
            parse_mode="Markdown",
            reply_markup=delete_keyboard,
        )
        return

    if action == "rewritelinkedin":
        pending_posts.pop(message_id, None)
        await query.edit_message_text("*Rewriting LinkedIn post...*", parse_mode="Markdown")
        post = generate_linkedin_post()
        source_url = post.get("source_url", "")
        preview = post["text"]
        if source_url:
            preview += f"\n\nSource: {source_url}"
        keyboard = [
            [InlineKeyboardButton("Post to LinkedIn", callback_data="postlinkedin"),
             InlineKeyboardButton("Rewrite", callback_data="rewritelinkedin")],
            [InlineKeyboardButton("Reject", callback_data="reject")],
        ]
        msg = await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"*LinkedIn Preview:*\n\n{preview}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
            link_preview_options=NO_PREVIEW,
        )
        pending_posts[msg.message_id] = {"text": post["text"], "source_url": source_url, "image_path": None, "linkedin_only": True}
        return

    # ── Standard post handlers ──
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
        await publish_post(text, image_path, message_id, context, source_url)

    elif action == "reject":
        pending_posts.pop(message_id, None)
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)
        tmp = await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Rejected.")
        asyncio.create_task(auto_delete_after(context.bot, TELEGRAM_CHAT_ID, tmp.message_id, 10))

    elif action == "rewrite":
        pending_posts.pop(message_id, None)
        await delete_msg(context.bot, TELEGRAM_CHAT_ID, message_id)
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
        "/thread — generate a viral thread\n"
        "/linkedin — long-form LinkedIn post\n"
        "/reply <tweet\\_url> — craft a reply to a tweet\n"
        "/meme — generate a coding meme\n"
        "/post your text here — preview your own post\n"
        "/history — last 10 published posts\n"
        "/queue — pending posts\n"
        "/ping — server status\n"
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


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import subprocess
    uptime_sec = int(time.time() - BOT_START_TIME)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    from src.history import load_history
    post_count = len(load_history())
    try:
        commit = subprocess.check_output(["git", "log", "-1", "--format=%h %s"], text=True).strip()
        last_updated = subprocess.check_output(["git", "log", "-1", "--format=%cr"], text=True).strip()
    except Exception:
        commit = "unknown"
        last_updated = "unknown"
    await update.message.reply_text(
        f"*pong.* bot is live.\n\n"
        f"uptime: {hours}h {minutes}m {seconds}s\n"
        f"version: `{commit}`\n"
        f"last updated: {last_updated}\n"
        f"pending approvals: {len(pending_posts)}\n"
        f"pending threads: {len(pending_threads)}\n"
        f"pending replies: {len(pending_replies)}\n"
        f"total posts published: {post_count}",
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


async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating a coding meme...")
    from src.memes import generate_meme
    post = generate_meme()
    if post:
        await send_for_approval(context.application, post)
    else:
        await update.message.reply_text("Meme generation failed. Try again.")


async def thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating a thread...")
    thread = generate_thread()
    tweets = thread["tweets"]
    source_url = thread.get("source_url", "")

    preview = "\n\n".join(f"*{i+1}.* {t}" for i, t in enumerate(tweets))
    if source_url:
        preview += f"\n\nSource: {source_url}"

    keyboard = [
        [
            InlineKeyboardButton("Post Thread", callback_data="postthread"),
            InlineKeyboardButton("Rewrite", callback_data="rewritethread"),
        ],
        [InlineKeyboardButton("Reject", callback_data="reject")],
    ]

    msg = await update.message.reply_text(
        f"*Thread Preview ({len(tweets)} tweets):*\n\n{preview}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        link_preview_options=NO_PREVIEW,
    )
    pending_threads[msg.message_id] = thread


async def linkedin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating LinkedIn post...")
    post = generate_linkedin_post()
    text = post["text"]
    source_url = post.get("source_url", "")

    preview = text
    if source_url:
        preview += f"\n\nSource: {source_url}"

    keyboard = [
        [
            InlineKeyboardButton("Post to LinkedIn", callback_data="postlinkedin"),
            InlineKeyboardButton("Rewrite", callback_data="rewritelinkedin"),
        ],
        [InlineKeyboardButton("Reject", callback_data="reject")],
    ]

    msg = await update.message.reply_text(
        f"*LinkedIn Preview:*\n\n{preview}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        link_preview_options=NO_PREVIEW,
    )
    pending_posts[msg.message_id] = {"text": text, "source_url": source_url, "image_path": None, "linkedin_only": True}


async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.replace("/reply", "", 1).strip()
    if not url or "status/" not in url:
        await update.message.reply_text("Usage: `/reply https://x.com/user/status/123`", parse_mode="Markdown")
        return

    await update.message.reply_text("Fetching tweet and crafting reply...")
    tweet = fetch_tweet_text(url)
    if not tweet:
        await update.message.reply_text("Couldn't fetch that tweet. Check the URL.")
        return

    reply_text = generate_reply(tweet["text"], tweet["author"])

    keyboard = [
        [
            InlineKeyboardButton("Reply Now", callback_data="sendreply"),
            InlineKeyboardButton("Rewrite", callback_data="rewritereply"),
        ],
        [InlineKeyboardButton("Reject", callback_data="reject")],
    ]

    msg = await update.message.reply_text(
        f"*Replying to @{tweet['author']}:*\n_{tweet['text'][:200]}_\n\n*Your reply:*\n{reply_text}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        link_preview_options=NO_PREVIEW,
    )
    pending_replies[msg.message_id] = {"reply_text": reply_text, "tweet": tweet}


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from src.history import load_history
    history = load_history()
    if not history:
        await update.message.reply_text("No posts yet.")
        return
    recent = history[-10:][::-1]
    lines = []
    for i, h in enumerate(recent, 1):
        text = h["text"][:60] + "..." if len(h["text"]) > 60 else h["text"]
        lines.append(f"*{i}.* {text}")
    await update.message.reply_text(
        f"*Last {len(recent)} posts:*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown",
        link_preview_options=NO_PREVIEW,
    )


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = []
    for mid, post in pending_posts.items():
        text = post["text"][:50] + "..." if len(post["text"]) > 50 else post["text"]
        scheduled = mid in scheduled_tasks
        status = "scheduled" if scheduled else "awaiting approval"
        items.append(f"- _{text}_ ({status})")
    for mid, thread in pending_threads.items():
        items.append(f"- Thread: _{thread['tweets'][0][:50]}..._ (awaiting approval)")
    for mid, reply in pending_replies.items():
        items.append(f"- Reply to @{reply['tweet']['author']} (awaiting approval)")
    if not items:
        await update.message.reply_text("Queue is empty.")
        return
    await update.message.reply_text(
        f"*Queue ({len(items)}):*\n\n" + "\n".join(items),
        parse_mode="Markdown",
        link_preview_options=NO_PREVIEW,
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_id = update.message.message_id
    deleted = 0
    for i in range(1, 100):
        try:
            await context.bot.delete_message(chat_id=TELEGRAM_CHAT_ID, message_id=msg_id - i)
            deleted += 1
        except Exception:
            continue
    try:
        await update.message.delete()
    except Exception:
        pass
    pending_posts.clear()
    pending_threads.clear()
    pending_replies.clear()
    tmp = await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"Cleared {deleted} messages.")
    asyncio.create_task(auto_delete_after(context.bot, TELEGRAM_CHAT_ID, tmp.message_id, 5))


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
