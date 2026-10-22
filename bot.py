"""
Telegram Referral Bot
- /start gives each user their own unique invite link
- tracks who referred whom in SQLite
- /stats shows a user's referral count
- /leaderboard shows top referrers
Setup: get a token from @BotFather, then run: BOT_TOKEN=123:abc python3 bot.py
"""

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import aiosqlite

BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = None  # filled at startup
DB_PATH = "referrals.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                referred_by INTEGER
            )"""
        )
        await db.commit()


async def get_bot_username(app):
    global BOT_USERNAME
    if BOT_USERNAME is None:
        me = await app.bot.get_me()
        BOT_USERNAME = me.username
    return BOT_USERNAME


def start_payload(referrer_id: int) -> str:
    return f"ref_{referrer_id}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None

    # parse ?start=ref_<id>
    if context.args and context.args[0].startswith("ref_"):
        try:
            referred_by = int(context.args[0][4:])
        except ValueError:
            referred_by = None
        if referred_by == user.id:
            referred_by = None  # can't refer yourself

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,))
        exists = await cur.fetchone()
        if not exists:
            await db.execute(
                "INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                (user.id, user.username, referred_by),
            )
            await db.commit()

    bot_username = await get_bot_username(context.application)
    link = f"https://t.me/{bot_username}?start={start_payload(user.id)}"

    count = await referral_count(user.id)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Share my link", url=f"https://t.me/share/url?url={link}")]]
    )
    await update.message.reply_text(
        f"hey {user.first_name}! ur personal invite link:\n\n{link}\n\n"
        f"people joined w ur link: {count}",
        reply_markup=keyboard,
    )


async def referral_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
        (count,) = await cur.fetchone()
    return count


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = await referral_count(update.effective_user.id)
    await update.message.reply_text(f"u've referred {count} people")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT u.username, u.user_id, COUNT(*) AS c
               FROM users u
               WHERE u.referred_by IS NOT NULL
               GROUP BY u.referred_by
               ORDER BY c DESC LIMIT 10"""
        )
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("no referrals yet, be the first")
        return
    lines = []
    for i, (username, uid, count) in enumerate(rows, 1):
        name = f"@{username}" if username else f"user {uid}"
        lines.append(f"{i}. {name} — {count}")
    await update.message.reply_text("top referrers:\n\n" + "\n".join(lines))


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(init_db).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
