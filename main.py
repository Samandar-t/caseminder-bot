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

# Kalitlar (Server muhitidan olinadi)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

logging.basicConfig(level=logging.INFO)

# Gemini AI sozlamasi
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Bazani yaratish
def init_db():
    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            case_details TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Men sizning shaxsiy case va invoice yordamchingizman.\n\n"
        "Yangi caseni yozib yuboring (masalan: 'Loyiha X uchun invoice kesilishi kerak').\n"
        "Ochiq caselarni ko'rish uchun /cases buyrug'ini bosing."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    prompt = f"Foydalanuvchi quyidagi case ma'lumotini yubordi: '{user_text}'. Ushbu casening qisqacha mazmunini va invoice holatini aniqlab, 1-2 jumla bilan tasdiqlang."
    response = model.generate_content(prompt)

    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cases (user_id, case_details) VALUES (?, ?)", (user_id, user_text))
    case_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ **Case #{case_id} saqlandi!**\n\n{response.text}\n\n"
        f"Men bu case va invoice bo'yicha holatni eslatib turaman."
    )

    # 4 soatdan keyin eslatma (14400 soniya)
    context.job_queue.run_once(
        send_reminder, 
        when=14400,
        data={"user_id": user_id, "case_id": case_id, "details": user_text},
        chat_id=update.effective_chat.id
    )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job()
    case_id = job.data["case_id"]
    details = job.data["details"]

    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM cases WHERE id = ?", (case_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0] == 'Pending':
        await context.bot.send_message(
            chat_id=job.chat_id,
            text=f"🔔 **ESLATMA / CASE #{case_id}**\n\n"
                 f"Ushbu case bo'yicha nima bo'ldi?\n📝 *'{details}'*\n\n"
                 f"Invoice kesildimi? /done_{case_id} buyrug'i orqali yopishingiz mumkin."
        )

async def list_cases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, case_details FROM cases WHERE user_id = ? AND status = 'Pending'", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Barcha caselar va invoicelar yopilgan! ✅")
        return

    msg = "📋 **Ochiq caselar:**\n\n"
    for row in rows:
        msg += f"• **Case #{row[0]}**: {row[1]} (/done_{row[0]})\n"
    await update.message.reply_text(msg)

async def complete_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    case_id = text.replace("/done_", "")
    
    conn = sqlite3.connect("cases.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE cases SET status = 'Completed' WHERE id = ?", (case_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🎉 **Case #{case_id} yopildi!**")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cases", list_cases))
    app.add_handler(MessageHandler(filters.Regex(r"^/done_\d+$"), complete_case))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
