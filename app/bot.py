# app/bot.py
from dotenv import load_dotenv
import os
load_dotenv()

import logging
import tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    ConversationHandler
)

from app.services.stt import transcribe
from app.services.sheets import append_offline_row
from app.services.validator import validate_and_normalize_row, prepare_row_for_sheet
from app.conversation_flow import ConversationState

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Conversation handler state
COLLECTING = 1


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "Бот готов. Отправляй голосовое, брат. Используй /help для команд."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "Отправляй текст или голосовое. После голосового -> "
        "бот транскрибирует и задаст пару быстрых вопросов."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command."""
    await update.message.reply_text("Отмена нахер.", reply_markup=ReplyKeyboardRemove())
    context.user_data.pop("conv_state", None)
    return ConversationHandler.END


# ============================================================================
# VOICE PROCESSING
# ============================================================================

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point: handle incoming voice message.
    Transcribes and starts data collection conversation.
    """
    msg = update.message
    await msg.reply_text("Получил голосовое. Скачиваю и транскрибирую...")
    
    # Download voice file
    voice = msg.voice or msg.audio
    if not voice:
        await msg.reply_text("Не нашел аудио че-та.")
        return ConversationHandler.END
    
    try:
        file = await context.bot.get_file(voice.file_id)
        temp_dir = tempfile.gettempdir()
        local_path = os.path.join(temp_dir, f"{voice.file_unique_id}.ogg")
        await file.download_to_drive(local_path)
        
        # Transcribe
        text = transcribe(local_path)
    except Exception as e:
        await msg.reply_text(f"Блять я захуярил голосовое: {str(e)}")
        return ConversationHandler.END
    
    # Check if transcription is empty
    if not text:
        await msg.reply_text(
            "Не смог нормально распознать голос — текст пустой. "
            "Я все равно сохраню визит, но без текста."
        )
    
    # Show transcription
    display_text = text[:800] + "..." if len(text) > 800 else text
    await msg.reply_text(f"Транскрибация: {display_text}")
    
    # Initialize conversation state
    conv_state = ConversationState(text, update.message.date)
    context.user_data["conv_state"] = conv_state
    
    # Ask first question
    question, keyboard = conv_state.get_next_question()
    if keyboard:
        await msg.reply_text(
            question, 
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
    else:
        await msg.reply_text(question, reply_markup=ReplyKeyboardRemove())
    
    return COLLECTING


# ============================================================================
# DATA COLLECTION
# ============================================================================

async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle user responses during data collection.
    Uses ConversationState to manage flow.
    """
    conv_state: ConversationState = context.user_data.get("conv_state")
    if not conv_state:
        await update.message.reply_text("Ошибка: состояние потеряно. Начни заново.")
        return ConversationHandler.END
    
    # Process the answer
    error = conv_state.process_answer(update.message.text)
    
    if error:
        # Validation error - ask again
        await update.message.reply_text(error)
        question, keyboard = conv_state.get_next_question()
        if keyboard:
            await update.message.reply_text(
                question,
                reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
            )
        else:
            await update.message.reply_text(question, reply_markup=ReplyKeyboardRemove())
        return COLLECTING
    
    # Check if complete
    if conv_state.is_complete():
        return await finalize_and_save(update, context, conv_state)
    
    # Ask next question
    question, keyboard = conv_state.get_next_question()
    if keyboard:
        await update.message.reply_text(
            question,
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
    else:
        await update.message.reply_text(question, reply_markup=ReplyKeyboardRemove())
    
    return COLLECTING


async def skip_short_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /skip command to skip short note."""
    conv_state: ConversationState = context.user_data.get("conv_state")
    if not conv_state:
        await update.message.reply_text("Ошибка: состояние потеряно.")
        return ConversationHandler.END
    
    conv_state.skip_short_note()
    return await finalize_and_save(update, context, conv_state)


# ============================================================================
# VALIDATION AND SAVING
# ============================================================================

async def finalize_and_save(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    conv_state: ConversationState
):
    """
    Validate collected data and save to Google Sheets.
    """
    # Validate the collected data
    is_valid, normalized_row, messages = validate_and_normalize_row(conv_state.data)
    
    if not is_valid:
        # Critical validation errors
        error_text = "❌ Ошибки валидации:\n" + "\n".join(messages)
        error_text += "\n\nДанные НЕ сохранены. Начни заново."
        await update.message.reply_text(error_text, reply_markup=ReplyKeyboardRemove())
        context.user_data.pop("conv_state", None)
        return ConversationHandler.END
    
    # Show warnings if any
    if messages:
        warning_text = "⚠️ Предупреждения:\n" + "\n".join(messages)
        await update.message.reply_text(warning_text)
    
    # Save to sheet
    try:
        # Use the new validator function to prepare the row
        append_offline_row(normalized_row)
        
        await update.message.reply_text(
            "✅ Забубенил в таблицу. Хорош братишка!",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        logging.error(f"Failed to save to sheet: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Бля че-то не вышло сохранить: {str(e)}\n\n"
            f"Проверь Google Sheets credentials и permissions."
        )
    
    # Clean up
    context.user_data.pop("conv_state", None)
    return ConversationHandler.END


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Start the bot."""
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Conversation handler
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.VOICE | filters.AUDIO, voice_handler)
        ],
        states={
            COLLECTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_data)
            ],
        },
        fallbacks=[
            CommandHandler("skip", skip_short_note),
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )
    
    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(conv)
    
    # Optional: Debug handler to see all incoming updates
    # Uncomment if you need debugging
    # async def _debug_all(update, context):
    #     print("===== UPDATE RECEIVED =====")
    #     print(update)
    # app.add_handler(MessageHandler(filters.ALL, _debug_all), group=-1)
    
    print("Бот щещес (готов)...")
    app.run_polling()


if __name__ == "__main__":
    main()