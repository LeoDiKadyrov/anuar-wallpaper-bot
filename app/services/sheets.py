# app/services/sheets.py
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from app.services.validator import SHEET_COLUMNS

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
    
    # Read actual header row from the sheet to get the correct column order
    header_row = ws.row_values(1)
    
    # Map values according to actual sheet column order
    values = []
    for col_name in header_row:
        # Normalize column name (strip whitespace, handle case variations)
        col_name_normalized = col_name.strip()
        # Try exact match first
        if col_name_normalized in row_dict:
            values.append(row_dict[col_name_normalized])
        else:
            # Try case-insensitive match
            found = False
            for key in row_dict.keys():
                if key.lower() == col_name_normalized.lower():
                    values.append(row_dict[key])
                    found = True
                    break
            if not found:
                # Column not found in row_dict, append empty string
                values.append("")
    
    ws.append_row(values, value_input_option="USER_ENTERED")
    return True