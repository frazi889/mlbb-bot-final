import json
import logging
import os
import re
import time
from typing import Optional, Tuple

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
BASE_WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_PATH = "telegram-webhook"

SEEN_FILE = "seen_receipts.json"
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


def load_seen_receipts() -> dict:
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_seen_receipts(data: dict) -> None:
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("Could not save seen receipts: %s", e)


SEEN_RECEIPTS = load_seen_receipts()


def cleanup_seen_receipts() -> None:
    now = int(time.time())
    expired = [k for k, ts in SEEN_RECEIPTS.items() if now - int(ts) > DUPLICATE_TTL]
    for k in expired:
        SEEN_RECEIPTS.pop(k, None)
    if expired:
        save_seen_receipts(SEEN_RECEIPTS)


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


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
        full_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
        if full_name:
            return full_name
    return "Unknown User"


def build_copy_text(id_value: str, server_value: str, package_value: Optional[str]) -> str:
    if package_value:
        return f".mlb {id_value}({server_value}){package_value}"
    return f".mlb {id_value}({server_value})"


def build_keyboard(copy_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="📋 Copy", copy_text=CopyTextButton(copy_text))]]
    )


def build_receipt_key(message, raw_text: str) -> str:
    """
    Duplicate = same receipt only
    - same photo/image file + same caption/text
    - or same plain text/caption message
    """
    text_key = normalize_text(raw_text)

    if getattr(message, "photo", None):
        return f"photo:{message.photo[-1].file_unique_id}|text:{text_key}"

    if getattr(message, "document", None):
        mime = getattr(message.document, "mime_type", "") or ""
        if mime.startswith("image/"):
            return f"docimg:{message.document.file_unique_id}|text:{text_key}"

    return f"text:{text_key}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("✅ MLBB Copy Bot Ready")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            f"Seen receipts: {len(SEEN_RECEIPTS)}\nDuplicate TTL: {DUPLICATE_TTL} seconds"
        )


async def clear_seen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    SEEN_RECEIPTS.clear()
    save_seen_receipts(SEEN_RECEIPTS)
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

    cleanup_seen_receipts()

    id_value, server_value = result
    package_value = extract_package(text)
    buyer_name = extract_name(message)

    receipt_key = build_receipt_key(message, text)

    now = int(time.time())
    last_seen = SEEN_RECEIPTS.get(receipt_key)

    if last_seen and (now - int(last_seen) <= DUPLICATE_TTL):
        await message.reply_text("ဒီပြေစာအရင်ပို့ဖူးပါတယ် ငွေပြန်စစ်ပါ")
        return

    SEEN_RECEIPTS[receipt_key] = now
    save_seen_receipts(SEEN_RECEIPTS)

    copy_text = build_copy_text(id_value, server_value, package_value)
    output = f"{buyer_name}\n{copy_text}"

    await message.reply_text(
        output,
        reply_markup=build_keyboard(copy_text),
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if not BASE_WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL is missing")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clearseen", clear_seen))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION | filters.PHOTO | filters.Document.IMAGE)
            & ~filters.COMMAND,
            handle_message,
        )
    )

    full_webhook_url = f"{BASE_WEBHOOK_URL}/{WEBHOOK_PATH}"

    print("Bot running with webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=full_webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
