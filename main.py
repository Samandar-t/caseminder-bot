import logging
import sqlite3
import os
import urllib.request
import json
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_text TEXT,
            english_text TEXT,
            status TEXT DEFAULT 'Open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def translate_with_gemini(text):
    if not GEMINI_API_KEY:
        return text
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    prompt_text = (
        f"Translate and rewrite the following dispatch note into a clean, professional English update. "
        f"Keep shop numbers, unit IDs, and technical terms accurate. Only return the final translated text:\n'{text}'"
    )
    data = {
        "contents": [{"parts": [{"text": prompt_text}]}]
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logging.error(f"Gemini Translation Error/Timeout: {e}")
        return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Case Bot ishga tushdi.\n\n"
        "• /newcase <matn> - Yangi case qo'shish\n"
        "• /casedone <ID> - Caseni yopish (Done)\n"
        "• /casecancel <ID> - Caseni bekor qilish (Cancel)\n"
        "• /caseupdates - Smenadagi ochiq caselarni ingliz tilida olish"
    )

async def new_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = " ".join(context.args)

    if not user_text:
        await update.message.reply_text("Iltimos, case matnini yuboring. Masalan:\n/newcase 3007 reefer unit")
        return

    # Tarjimani olish (Maksimal 5 soniya kutadi)
    translated_text = translate_with_gemini(user_text)

    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cases (user_id, original_text, english_text) VALUES (?, ?, ?)",
        (user_id, user_text, translated_text)
    )
    case_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ **Case #{case_id} caselar qatoriga qo'shildi!**",
        parse_mode="Markdown"
    )

async def case_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Iltimos, case ID sini yuboring. Masalan: /casedone 1")
        return

    case_id = context.args[0]
    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE cases SET status = 'Done' WHERE id = ?", (case_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🎉 **Case #{case_id} marked as DONE!**")

async def case_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Iltimos, case ID sini yuboring. Masalan: /casecancel 1")
        return

    case_id = context.args[0]
    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE cases SET status = 'Cancelled' WHERE id = ?", (case_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🚫 **Case #{case_id} CANCELLED**")

async def case_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, english_text, status FROM cases WHERE user_id = ? AND status = 'Open'",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("✨ Smenangizda ochiq caselar yo'q!")
        return

    report = "📢 **SHIFT UPDATES / UNRESOLVED ISSUES**\n"
    report += "──────────────────────────\n\n"
    for row in rows:
        case_id, eng_text, status = row
        report += f"🔹 **Case #{case_id}**\n"
        report += f"📝 {eng_text}\n"
        report += f"⚡ Actions: `/casedone {case_id}` | `/casecancel {case_id}`\n\n"

    report += "──────────────────────────\n"
    report += "ℹ️ *Updates guruhiga tashlash uchun nusxalab oling.*"

    await update.message.reply_text(report, parse_mode="Markdown")

async def list_cases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await case_updates(update, context)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newcase", new_case))
    app.add_handler(CommandHandler("casedone", case_done))
    app.add_handler(CommandHandler("casecancel", case_cancel))
    app.add_handler(CommandHandler("caseupdates", case_updates))
    app.add_handler(CommandHandler("cases", list_cases))
    
    app.run_polling()
