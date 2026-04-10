import os
import re
import time
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN")
SEEN_FILE = "seen_receipts.json"

# ================= LOAD / SAVE =================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return json.load(f)
    return {}

def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f)

SEEN_RECEIPTS = load_seen()

# ================= RECEIPT KEY =================
def extract_receipt_key(text):
    text_l = text.lower()

    amount = ""
    m_amount = re.search(r"(-?\d[\d,\.]+)\s*ks", text_l)
    if m_amount:
        amount = m_amount.group(1)

    txid = ""
    m_tx = re.search(r"\b\d{10,}\b", text_l)
    if m_tx:
        txid = m_tx.group(0)

    date = ""
    m_date = re.search(r"\d{2}[./-]\d{2}[./-]\d{4}", text_l)
    if m_date:
        date = m_date.group(0)

    return f"{amount}_{txid}_{date}"

# ================= ID EXTRACT =================
def extract_ids(text):
    return re.findall(r"\d{5,}", text)

# ================= PACKAGE =================
def extract_package(text):
    packages = ["86", "172", "257", "344", "429", "514", "600"]
    for p in packages:
        if p in text:
            return p
    return ""

# ================= FORMAT =================
def format_result(id_value, server_value, package_value):
    if package_value:
        return f".mlb {id_value}({server_value}) {package_value}"
    return f".mlb {id_value}({server_value})"

# ================= COMMAND =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot Ready!")

async def clear_seen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    SEEN_RECEIPTS.clear()
    save_seen(SEEN_RECEIPTS)
    await update.message.reply_text("🧹 Cleared receipts")

# ================= MAIN =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    text = ""
    if message.text:
        text += message.text + "\n"
    if message.caption:
        text += message.caption

    text = text.strip()
    if not text:
        return

    # ===== receipt detect =====
    receipt_key = extract_receipt_key(text)

    if receipt_key != "__" and receipt_key in SEEN_RECEIPTS:
        await message.reply_text(
            "⚠️ သတိပေးချက်\n"
            "ဒီပြေစာသည် အရင်ပို့ထားသော ပြေစာနှင့် တူနေပါသည်။\n"
            "ငွေစာရင်းကို ပြန်စစ်ပြီးမှ ဆက်လုပ်ပါ။"
        )
        return

    if receipt_key != "__":
        SEEN_RECEIPTS[receipt_key] = int(time.time())
        save_seen(SEEN_RECEIPTS)

    # ===== extract ids =====
    ids = extract_ids(text)
    if not ids:
        return

    # ===== server =====
    server = "1"
    if "(" in text and ")" in text:
        try:
            server = text.split("(")[1].split(")")[0]
        except:
            pass

    package = extract_package(text)

    results = []
    for i in ids:
        results.append(format_result(i, server, package))

    final_text = "\n".join(results)

    await message.reply_text(final_text)

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clearseen", clear_seen))
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("Bot running...")
    app.run_polling()
