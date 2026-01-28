# app/bot.py
from dotenv import load_dotenv
import os
import re
load_dotenv()
import logging
import tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from app.services.stt import transcribe
from app.services.sheets import append_offline_row
from app.services.validator import normalize_offline_row

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Conversation states
CHOOSING_EXTRA, SHORT_NOTE = range(2)

# Quick keyboards (match your lists)
TYPE_CLIENT_KB = [["новый"], ["повторный"], ["контрактник/мастер"], ["оптовик"]]
BEHAVIOR_KB = [["мимо прошли"], ["поспрашивали"], ["посмотрели"], ["замеряли/считали"]]
STATUS_KB = [["купили"], ["не купили"], ["думают"], ["обмен"]]
YESNO_KB = [["да"], ["нет"]]


def _guess_quantity_from_transcription(text: str) -> str:
    """
    Очень простой хелпер: пытается вытащить первое число из транскрибации,
    чтобы хотя бы примерно проставить Quantity.
    Если ничего не нашел — вернет пустую строку.
    """
    if not text:
        return ""
    m = re.search(r"\d+(?:[.,]\d+)?", text)
    if not m:
        return ""
    return m.group(0).replace(",", ".")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот готов. Отправляй голосовое, брат. Используй /help для команд.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправляй текст или голосовое. После голосового -> бот транскрибирует и задаст пару быстрых вопросов.")

# Entry: voice message
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await msg.reply_text("Получил голосовое. Скачиваю и транскрибирую...")
    voice = msg.voice or msg.audio
    if not voice:
        await msg.reply_text("Не нашел аудио че-та.")
        return

    file = await context.bot.get_file(voice.file_id)
    temp_dir = tempfile.gettempdir()
    local_path = os.path.join(temp_dir, f"{voice.file_unique_id}.ogg")
    await file.download_to_drive(local_path)

    try:
        text = transcribe(local_path)
    except Exception as e:
        await msg.reply_text("Блять я захуярил голосовое: " + str(e))
        text = ""

    # Явно подсветим случай, когда ничего не распознано
    if not text:
        await msg.reply_text("Не смог нормально распознать голос — текст пустой. Я все равно сохраню визит, но без текста.")

    # Pre-fill a row dict in user_data
    quantity_guess = _guess_quantity_from_transcription(text)
    row = {
        "Date": update.message.date.date().isoformat(),
        "Time": update.message.date.time().strftime("%H:%M"),
        "Transcription_raw": text,  # сырая транскрибация для анализа в таблице
        "Client_ID": "",
        "Type_of_client": "",
        "Behavior": "",
        "Purchase_status": "",
        "Ticket_amount": "",
        "Cost_Price": "",
        "Source": "",
        "Reason_not_buying": "",
        "Product_name": "",
        "Quantity": quantity_guess,
        "Repeat_visit": "",
        "Contact_left": "",
        "Short_note": "",
    }
    context.user_data["pending_row"] = row

    # Send transcription and ask first quick question
    await msg.reply_text("Транскрибация: " + (text[:800] + "..." if len(text)>800 else text))
    await msg.reply_text("Выбери баля Type_of_client", reply_markup=ReplyKeyboardMarkup(TYPE_CLIENT_KB, one_time_keyboard=True))
    return CHOOSING_EXTRA

async def choosing_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    row = context.user_data.get("pending_row", {})
    # Determine which field is being answered based on what is empty
    if not row.get("Type_of_client"):
        row["Type_of_client"] = text
        await update.message.reply_text("Че он делал? Behavior", reply_markup=ReplyKeyboardMarkup(BEHAVIOR_KB, one_time_keyboard=True))
    elif not row.get("Behavior"):
        row["Behavior"] = text
        await update.message.reply_text("Купил или не купил? Purchase status?", reply_markup=ReplyKeyboardMarkup(STATUS_KB, one_time_keyboard=True))
    elif not row.get("Purchase_status"):
        row["Purchase_status"] = text
        tnorm = (text or "").lower().strip()
        if tnorm == "купили":
            await update.message.reply_text("Че там брат насколько наторговал? Если не знаешь отправляй 0, если знаешь отправляй сумму", reply_markup=ReplyKeyboardRemove())
            return SHORT_NOTE
        else:
            await update.message.reply_text("А че не купили? Почему? Отправляй пункты из списка или напиши коротко", reply_markup=ReplyKeyboardMarkup([["дорого"],["нет дизайна/цвета"],["нет в наличии"],["сравнивают"],["зайдут позже"],["не целевой"], ["не успел обработать"], ["другое"]], one_time_keyboard=True))
    # Блок для тех, кто НЕ купил: причина -> контакт -> источник -> комментарий
    elif row.get("Purchase_status") != "купили" and not row.get("Reason_not_buying"):
        row["Reason_not_buying"] = text
        await update.message.reply_text("Хотя бы контакт оставил? (да/нет)", reply_markup=ReplyKeyboardMarkup(YESNO_KB, one_time_keyboard=True))
    elif row.get("Purchase_status") != "купили" and not row.get("Contact_left"):
        row["Contact_left"] = text
        await update.message.reply_text(
            "Откуда он узнал про наш секретный бутик обоев? (Source)",
            reply_markup=ReplyKeyboardMarkup(
                [["Instagram"], ["2ГИС"], ["рекомендация"], ["вывеска"], ["TikTok"], ["другое"]],
                one_time_keyboard=True,
            ),
        )
    elif row.get("Purchase_status") != "купили" and not row.get("Source"):
        row["Source"] = text
        await update.message.reply_text("Ну в кратце расскажи что-то еще, а если нечего то /skip", reply_markup=ReplyKeyboardRemove())
        return SHORT_NOTE
    # Блок для тех, кто КУПИЛ: после суммы мы сюда еще вернемся только за Source
    elif row.get("Purchase_status") == "купили" and not row.get("Source"):
        row["Source"] = text
        await update.message.reply_text(
            "Что именно продали и в каком количестве? Например: 'флизелиновые обои, 3 рулона'",
            reply_markup=ReplyKeyboardRemove(),
        )
        return SHORT_NOTE

    context.user_data["pending_row"] = row
    return CHOOSING_EXTRA

async def short_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = context.user_data.get("pending_row", {})
    text_raw = update.message.text or ""
    text = text_raw.strip()

    def parse_number(s: str):
        if s is None:
            return None

        s2 = s.strip()
        if s2 == "":
            return None
        try:
            return float(s2.replace(",", "."))
        except Exception:
            return None

    # Ветка для покупателей: сначала выжимаем максимум структурных полей,
    # и только ПОТОМ просим комментарий.
    if row.get("Purchase_status") == "купили":
        # 1) Оборот (Ticket_amount)
        if row.get("Ticket_amount", "") == "":
            num = parse_number(text)
            row["Ticket_amount"] = num if num is not None else text  # если не число — как есть
            await update.message.reply_text(
                "Че там брат СЕБЕСТОИМОСТЬ? Если не знаешь отправляй 0, если знаешь отправляй сумму",
                reply_markup=ReplyKeyboardRemove(),
            )
            context.user_data["pending_row"] = row
            return SHORT_NOTE

        # 2) Себестоимость (Cost_Price)
        if row.get("Cost_Price", "") == "":
            num = parse_number(text)
            row["Cost_Price"] = num if num is not None else text
            await update.message.reply_text(
                "Откуда он узнал про наш секретный бутик обоев? (Source)",
                reply_markup=ReplyKeyboardMarkup(
                    [["Instagram"], ["2ГИС"], ["рекомендация"], ["вывеска"], ["TikTok"], ["другое"]],
                    one_time_keyboard=True,
                ),
            )
            context.user_data["pending_row"] = row
            return CHOOSING_EXTRA

        # 3) Что продали и сколько (Product_name, Quantity)
        if row.get("Product_name", "") == "":
            # Пытаемся вытащить количество из введенного текста,
            # если Quantity не был угадан по транскрибации.
            #qty = row.get("Quantity", "") or _guess_quantity_from_transcription(text)
            m = re.search(r"\d+(?:[.,]\d+)?", text)
            if m:
                qty = m.group(0).replace(",", ".")
                product_name = (text[:m.start()] + text[m.end():]).strip(" ,.-")
            else:
                qty = row.get("Quantity", "") or ""
                product_name = text
            row["Product_name"] = product_name
            row["Quantity"] = qty

            await update.message.reply_text(
                "Ну в кратце расскажи что-то еще, а если нечего то /skip",
                reply_markup=ReplyKeyboardRemove(),
            )
            context.user_data["pending_row"] = row
            return SHORT_NOTE

    # Общий случай: это уже действительно комментарий
    row["Short_note"] = text
    context.user_data["pending_row"] = row
    # finalize: append to sheet
    try:
        append_offline_row(row)
        await update.message.reply_text("Забубенил в таблицу. Хорош братишка!", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await update.message.reply_text("Бля че-то не вышло сохранить: " + str(e))
    context.user_data.pop("pending_row", None)
    return ConversationHandler.END

async def skip_short_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = context.user_data.get("pending_row", {})
    row["Short_note"] = ""
    try:
        append_offline_row(row)
        await update.message.reply_text("Сохранил без твоих гениальных комментариев.", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await update.message.reply_text("Бля че-то не вышло сохранить: " + str(e))
    context.user_data.pop("pending_row", None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отмена нахер.", reply_markup=ReplyKeyboardRemove())
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
    print("Бот щещес (готов)...")

    async def _debug_all(update, context):
        print("===== UPDATE RECEIVED =====")
        print(update)
        # optional: reply so you immediately see a response
        try:
            if update.message:
                await update.message.reply_text("debug: got your message")
        except Exception as e:
            print("debug reply failed:", e)

    app.add_handler(MessageHandler(filters.ALL, _debug_all), group=-1)
    app.run_polling()

if __name__ == "__main__":
    main()