import json
import logging
import os
import re
import time
from typing import Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.onrender.com

SEEN_FILE = "seen_orders.json"
DUPLICATE_TTL = 43200  # 12 hours

ID_SERVER_PATTERNS = [
    re.compile(r"\b(\d{6,14})\s*\((\d{3,8})\)"),
    re.compile(r"\b(\d{6,14})\s*/\s*(\d{3,8})"),
]

KEYWORDS = [
    "twilight pass", "weekly elite", "monthly epic",
    "500+500", "250+250", "150+150", "50+50",
    "11483", "9288", "5532", "4390", "3688", "2901", "2195",
    "1755", "1584", "1412", "1220", "1135", "1049", "963",
    "878", "792", "706", "600", "514", "429", "344", "343",
    "257", "172", "110", "86", "wp"
]


def load_seen_orders() -> dict:
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_seen_orders(data: dict) -> None:
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("Could not save seen orders: %s", e)


SEEN_ORDERS = load_seen_orders()


def cleanup_seen_orders() -> None:
    now = int(time.time())
    expired = [k for k, ts in SEEN_ORDERS.items() if now - int(ts) > DUPLICATE_TTL]
    for k in expired:
        SEEN_ORDERS.pop(k, None)
    if expired:
        save_seen_orders(SEEN_ORDERS)


def contains_keyword(text: str) -> bool:
    text_l = text.lower()
    return any(k in text_l for k in KEYWORDS)


def extract_id_server(text: str) -> Optional[Tuple[str, str]]:
    for pattern in ID_SERVER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1), match.group(2)
    return None


def extract_package(text: str) -> Optional[str]:
    text_l = text.lower()

    m1 = re.search(r"\bwp\s*(\d+)\b", text_l)
    if m1:
        return f"{m1.group(1)}wp"

    m2 = re.search(r"\b(\d+)\s*wp\b", text_l)
    if m2:
        return f"{m2.group(1)}wp"

    special_packages = [
        "twilight pass",
        "weekly elite",
        "monthly epic",
        "500+500",
        "250+250",
        "150+150",
        "50+50",
    ]
    for item in special_packages:
        if item in text_l:
            return item

    numeric_packages = [
        "11483", "9288", "5532", "4390", "3688", "2901", "2195",
        "1755", "1584", "1412", "1220", "1135", "1049", "963",
        "878", "792", "706", "600", "514", "429", "344", "343",
        "257", "172", "110", "86"
    ]
    for item in numeric_packages:
        if re.search(rf"\b{re.escape(item)}\b", text_l):
            return item

    if re.search(r"\bwp\b", text_l):
        return "wp"

    return None


def extract_name(message) -> str:
    user = message.from_user
    if user:
        if user.username:
            return f"@{user.username}"
        full_name = " ".join(
            part for part in [user.first_name, user.last_name] if part
        ).strip()
        if full_name:
            return full_name
    return "Unknown User"


def build_keyboard(id_value: str, server_value: str, package_value: Optional[str]) -> InlineKeyboardMarkup:
    if package_value:
        copy_text = f"{id_value}({server_value}){package_value}"
    else:
        copy_text = f"{id_value}({server_value})"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Copy", switch_inline_query_current_chat=copy_text)]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("✅ MLBB Copy Bot Ready")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            f"Seen orders: {len(SEEN_ORDERS)}\nDuplicate TTL: {DUPLICATE_TTL} seconds"
        )


async def clear_seen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    SEEN_ORDERS.clear()
    save_seen_orders(SEEN_ORDERS)
    if update.message:
        await update.message.reply_text("🧹 Duplicate list cleared")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    text = ""
    if message.text:
        text += message.text + "\n"
    if message.caption:
        text += message.caption

    text = text.strip()
    if not text:
        return

    result = extract_id_server(text)
    if not result:
        return

    if not contains_keyword(text):
        return

    cleanup_seen_orders()

    id_value, server_value = result
    package_value = extract_package(text)
    buyer_name = extract_name(message)

    if package_value:
        order_key = f"{id_value}({server_value}) {package_value}".lower()
    else:
        order_key = f"{id_value}({server_value})".lower()

    now = int(time.time())
    last_seen = SEEN_ORDERS.get(order_key)

    if last_seen and (now - int(last_seen) <= DUPLICATE_TTL):
        if package_value:
            alert_text = f"⚠️ Duplicate Receipt\n{buyer_name}\n{id_value}({server_value}){package_value}"
        else:
            alert_text = f"⚠️ Duplicate Receipt\n{buyer_name}\n{id_value}({server_value})"

        await message.reply_text(alert_text)
        return

    SEEN_ORDERS[order_key] = now
    save_seen_orders(SEEN_ORDERS)

    if package_value:
        output = f"{buyer_name}\n{id_value}({server_value}){package_value}"
    else:
        output = f"{buyer_name}\n{id_value}({server_value})"

    await message.reply_text(
        output,
        reply_markup=build_keyboard(id_value, server_value, package_value),
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL is missing")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clearseen", clear_seen))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            handle_message,
        )
    )

    print("Bot running with webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
