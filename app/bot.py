import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from services.stt import speech_to_text
from services.sheets import append_offline_row

TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot ready. Send voice or text.")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    # download file
    file = await context.bot.get_file(voice.file_id)
    path = f"/tmp/{voice.file_id}.ogg"
    await file.download_to_drive(path)
    text = speech_to_text(path)  # implement in services/stt.py
    # append to Google Sheets
    append_offline_row({
        "Date": update.message.date.date().isoformat(),
        "Time": update.message.date.time().strftime("%H:%M"),
        "Transcription_raw": text,
        # other fields left blank or filled by prompts
    })
    await update.message.reply_text("Saved. Text: " + text[:200])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.run_polling()
