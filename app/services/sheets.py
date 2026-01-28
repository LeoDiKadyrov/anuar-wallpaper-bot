# app/services/sheets.py
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SHEET_NAME = os.getenv("SPREADSHEET_NAME", "Anuar Traffic 2026")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "./credentials.json")

def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDS_JSON, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open(SHEET_NAME)
    return sh

def append_offline_row(row_dict: dict):
    """
    row_dict keys:
    Date, Time, Client_ID, Type_of_client, Behavior, Purchase_status, Ticket_amount, Cost_Price, Source, 
    Reason_not_buying, Product_name, Quantity, Transcription_raw, Repeat_visit, Contact_left, Short_note
    """
    sh = get_sheet()
    ws = sh.worksheet("Offline Traffic")
    # Ensure header order matches
    header = ws.row_values(1)
    # Map values in header order
    values = []
    for h in header:
        values.append(row_dict.get(h, ""))
    ws.append_row(values, value_input_option="USER_ENTERED")
    return True