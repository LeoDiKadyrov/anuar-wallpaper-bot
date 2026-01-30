# app/services/sheets.py
import gspread
from google.oauth2.service_account import Credentials
from app.services.validator import SHEET_COLUMNS
from app.config import SPREADSHEET_NAME, GOOGLE_CREDENTIALS_JSON

def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_JSON, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open(SPREADSHEET_NAME)
    return sh

def append_offline_row(row_dict: dict):
    """
    row_dict keys:
    Date, Time, Client_ID, Type_of_client, Behavior, Purchase_status, Ticket_amount, Cost_Price, Source, 
    Reason_not_buying, Product_name, Quantity, Transcription_raw, Repeat_visit, Contact_left, Short_note
    """
    sh = get_sheet()
    ws = sh.worksheet("Offline Traffic")

    try:
        headers = ws.row_values(1)
    except Exception:
        # Если таблица пустая, используем дефолтные из валидатора (fallback)
        from app.services.validator import SHEET_COLUMNS
        headers = SHEET_COLUMNS

    if not headers:
        # На случай если row_values вернул пустой список
        from app.services.validator import SHEET_COLUMNS
        headers = SHEET_COLUMNS

    # 2. Собираем данные строго в порядке заголовков таблицы
    values = []
    for header in headers:
        col_name = header.strip()
        
        # Ищем значение в словаре (с учетом регистра)
        val = ""
        if col_name in row_dict:
            val = row_dict[col_name]
        else:
            # Если прямого совпадения нет, ищем case-insensitive
            for k, v in row_dict.items():
                if k.lower() == col_name.lower():
                    val = v
                    break
        
        values.append(val)
    
    # 3. Вычисляем номер строки для записи
    # Чтобы не привязываться к столбцу A (который может быть пустым),
    # найдем индекс столбца "Date" и посчитаем строки по нему.
    try:
        # Ищем столбец с названием "Date" или "Дата" (регистронезависимо)
        date_col_index = -1
        for idx, h in enumerate(headers):
            if "date" in h.lower() or "дата" in h.lower():
                date_col_index = idx + 1 # gspread использует индексацию с 1
                break
        
        if date_col_index == -1:
            date_col_index = 1 # Если не нашли, по дефолту смотрим 1-й столбец
            
        filled_rows = len(ws.col_values(date_col_index))
        next_row = filled_rows + 1
    except Exception:
        next_row = 2

    # 4. Записываем данные
    # update("A...", ...) начнет писать с самого первого столбца.
    # Так как мы собрали values на основе headers (включая пустые заголовки слева),
    # данные лягут ровно под свои шапки.
    cell_range = f"A{next_row}"
    ws.update(cell_range, [values], value_input_option="USER_ENTERED")
    
    return True