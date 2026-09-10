import logging
import sqlite3
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import google.generativeai as genai

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

logging.basicConfig(level=logging.INFO)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Yangilangan Case Bot ishga tushdi.\n\n"
        "Buyruqlar:\n"
        "• /newcase <matn> - Yangi case qo'shish (Ingliz tiliga tarjima qilinadi)\n"
        "• /casedone <ID> - Caseni yopish (Done)\n"
        "• /casecancel <ID> - Caseni bekor qilish (Cancelled/Take care)\n"
        "• /caseupdates - Smenadagi ochiq caselar hisobotini olish\n"
        "• /cases - Barcha ochiq caselar ro'yxati"
    )

async def new_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = " ".join(context.args)

    if not user_text:
        await update.message.reply_text("Iltimos, case matnini yazing. Masalan: /newcase Unit 102 invoice berilishi kerak fast delivery")
        return

    # Gemini AI orqali aralash matnni professional ingliz tiliga o'girish
    prompt = (
        f"Translate and rewrite the following mixed language text into a clear, professional English dispatch/customer support note. "
        f"Keep unit numbers, store details, and technical terms accurate.\nText: '{user_text}'"
    )
    response = model.generate_content(prompt)
    translated_text = response.text.strip()

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
        f"✅ **Case #{case_id} Created**\n\n"
        f"📌 **Translated English Note:**\n{translated_text}\n\n"
        f" Status: `Open`\n"
        f" To mark Done: `/casedone {case_id}`\n"
        f" To Cancel: `/casecancel {case_id}`",
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

    await update.message.reply_text(f"🚫 **Case #{case_id} CANCELLED** (Customer took care / No shop needed).")

async def case_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, english_text, status, created_at FROM cases WHERE user_id = ? AND status = 'Open'",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("✨ Smenangizda barcha caselar bajarilgan! Ochiq yoki hal bo'lmagan issue'lar yo'q.")
        return

    report = "📢 **SHIFT UPDATES / UNRESOLVED ISSUES**\n"
    report += "──────────────────────────\n\n"
    for row in rows:
        case_id, eng_text, status, created_at = row
        report += f"🔹 **Case #{case_id}** [Status: {status}]\n"
        report += f"📝 {eng_text}\n"
        report += f"⚡ Quick action: `/casedone {case_id}` | `/casecancel {case_id}`\n\n"

    report += "──────────────────────────\n"
    report += "ℹ️ *Copy and paste this message directly into the Updates group.*"

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
