# app/bot.py
import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from services.stt import transcribe
from services.sheets import append_offline_row

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Conversation states
CHOOSING_EXTRA, SHORT_NOTE = range(2)

# Quick keyboards (match your lists)
TYPE_CLIENT_KB = [["New"], ["Repeat"], ["Master/Contractor"], ["Wholesale"]]
BEHAVIOR_KB = [["just_entered"], ["asked"], ["browsing"], ["measuring"]]
STATUS_KB = [["bought"], ["not_bought"], ["considering"]]
YESNO_KB = [["yes"], ["no"]]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot ready. Send voice message to log a visit. Use /help for commands.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send voice or text. After voice -> bot will transcribe and ask quick questions to fill the row.")

# Entry: voice message
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await msg.reply_text("Received voice. Downloading and transcribing...")
    voice = msg.voice or msg.audio
    if not voice:
        await msg.reply_text("No audio found.")
        return

    file = await context.bot.get_file(voice.file_id)
    local_path = f"/tmp/{voice.file_unique_id}.ogg"
    await file.download_to_drive(local_path)

    try:
        text = transcribe(local_path)
    except Exception as e:
        await msg.reply_text("Transcription failed: " + str(e))
        text = ""

    # Pre-fill a row dict in user_data
    row = {
        "Date": update.message.date.date().isoformat(),
        "Time": update.message.date.time().strftime("%H:%M"),
        "Transcription_raw": text,
        "Client_ID": "", "Type_of_client": "", "Behavior": "",
        "Purchase_status": "", "Ticket_amount": "", "Reason_not_buying": "",
        "Product_name": "", "Quantity": "", "Repeat_visit": "", "Contact_left": "", "Short_note": ""
    }
    context.user_data["pending_row"] = row

    # Send transcription and ask first quick question
    await msg.reply_text("Transcription: " + (text[:800] + "..." if len(text)>800 else text))
    await msg.reply_text("Choose Type_of_client", reply_markup=ReplyKeyboardMarkup(TYPE_CLIENT_KB, one_time_keyboard=True))
    return CHOOSING_EXTRA

async def choosing_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    row = context.user_data.get("pending_row", {})
    # Determine which field is being answered based on what is empty
    if not row.get("Type_of_client"):
        row["Type_of_client"] = text
        await update.message.reply_text("Choose Behavior", reply_markup=ReplyKeyboardMarkup(BEHAVIOR_KB, one_time_keyboard=True))
    elif not row.get("Behavior"):
        row["Behavior"] = text
        await update.message.reply_text("Purchase status?", reply_markup=ReplyKeyboardMarkup(STATUS_KB, one_time_keyboard=True))
    elif not row.get("Purchase_status"):
        row["Purchase_status"] = text
        if text == "bought":
            await update.message.reply_text("Enter ticket amount (number) or send 0 if unknown", reply_markup=ReplyKeyboardRemove())
            return SHORT_NOTE
        else:
            await update.message.reply_text("Reason for not buying? (choose or type short reason)", reply_markup=ReplyKeyboardMarkup([["price"],["no_design"],["out_of_stock"],["comparing"],["later"],["not_target"]], one_time_keyboard=True))
    elif not row.get("Reason_not_buying"):
        row["Reason_not_buying"] = text
        await update.message.reply_text("Did client leave contact? (yes/no)", reply_markup=ReplyKeyboardMarkup(YESNO_KB, one_time_keyboard=True))
    elif not row.get("Contact_left"):
        row["Contact_left"] = text
        await update.message.reply_text("Short note (3-6 words) or send /skip", reply_markup=ReplyKeyboardRemove())
        return SHORT_NOTE

    context.user_data["pending_row"] = row
    return CHOOSING_EXTRA

async def short_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = context.user_data.get("pending_row", {})
    text = update.message.text.strip()
    # If expecting ticket amount
    if row.get("Purchase_status") == "bought" and not row.get("Ticket_amount"):
        # try parse number
        try:
            amt = float(text)
            row["Ticket_amount"] = amt
        except:
            row["Ticket_amount"] = text  # raw if failed
        # next ask contact
        await update.message.reply_text("Did client leave contact? (yes/no)", reply_markup=ReplyKeyboardMarkup(YESNO_KB, one_time_keyboard=True))
        return CHOOSING_EXTRA
    # Otherwise treat as short_note
    row["Short_note"] = text
    context.user_data["pending_row"] = row
    # finalize: append to sheet
    try:
        append_offline_row(row)
        await update.message.reply_text("Saved to sheet. Thanks!", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await update.message.reply_text("Failed to save: " + str(e))
    context.user_data.pop("pending_row", None)
    return ConversationHandler.END

async def skip_short_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = context.user_data.get("pending_row", {})
    row["Short_note"] = ""
    try:
        append_offline_row(row)
        await update.message.reply_text("Saved without note.", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await update.message.reply_text("Failed to save: " + str(e))
    context.user_data.pop("pending_row", None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    context.user_data.pop("pending_row", None)
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.VOICE | filters.AUDIO, voice_handler)],
        states={
            CHOOSING_EXTRA: [MessageHandler(filters.TEXT & ~filters.COMMAND, choosing_extra)],
            SHORT_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, short_note_handler)]
        },
        fallbacks=[CommandHandler("skip", skip_short_note), CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(conv)
    print("Bot polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
