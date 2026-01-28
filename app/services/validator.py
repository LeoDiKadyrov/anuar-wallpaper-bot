# app/services/validator.py
import re
from typing import Tuple, Dict, Any, List, Optional
from difflib import get_close_matches
import math

# --- CONFIG: allowed lists (подгони под свою таблицу) ---
ALLOWED = {
    "Type_of_client": ["новый", "повторный", "контрактник/мастер", "оптовик"],
    "Behavior": ["мимо прошли", "поспрашивали", "посмотрели", "замеряли/считали"],
    "Purchase_status": ["купили", "не купили", "думают", "обмен"],
    "Reason_not_buying": ["дорого", "нет дизайна/цвета", "нет в наличии", "сравнивают",
                         "зайдут позже", "не целевой", "не успел обработать", "другое"],
    "Source": ["Instagram", "2ГИС", "рекомендация", "вывеска", "TikTok", "другое"],
    "YesNo": ["да", "нет"]
}

# --- Helpers ---
_digits_re = re.compile(r"\d+([.,]\d+)?")
_phone_digits = re.compile(r"\d+")

def norm_text(s: Optional[str]) -> str:
    if s is None:
        return ""
    s = str(s)
    # remove dangerous characters, keep punctuation minimal
    s = s.replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)  # collapse spaces
    # optionally remove weird control characters
    s = re.sub(r"[^\x20-\x7E\u0400-\u04FFА-Яа-яёЁ–—…,-.:()/%]+", "", s)
    return s.strip()

def parse_number(s: Optional[str]) -> Optional[float]:
    """Try to parse a number; return float or None."""
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    # remove currency symbols and letters except digits, dot, comma, minus
    s_clean = re.sub(r"[^\d,.\-]", "", s)
    # if multiple separators, keep last dot/comma as decimal separator
    if s_clean.count(",") + s_clean.count(".") > 1:
        # replace all commas with nothing, then replace last dot with decimal
        s_clean = s_clean.replace(",", "")
    s_clean = s_clean.replace(",", ".")
    try:
        val = float(s_clean)
        if math.isfinite(val):
            return val
    except Exception:
        return None
    return None

def parse_int(s: Optional[str]) -> Optional[int]:
    f = parse_number(s)
    if f is None:
        return None
    return int(round(f))

def norm_phone(s: Optional[str]) -> str:
    if not s:
        return ""
    digits = "".join(_phone_digits.findall(str(s)))
    # keep last 9..12 digits (local variation). Adjust rule if you want country codes.
    if len(digits) >= 9:
        return digits[-12:]
    return digits

def match_enum(s: Optional[str], key: str, cutoff: float = 0.6) -> str:
    """Map free text to allowed enum; if no match, return '' or 'другое' if allowed."""
    s0 = norm_text(s).lower()
    if not s0:
        return ""
    choices = ALLOWED.get(key, [])
    # exact match ignoring case
    for c in choices:
        if s0 == c.lower():
            return c
    # try simple substring match
    for c in choices:
        if s0 in c.lower() or c.lower() in s0:
            return c
    # fuzzy match
    names = choices
    matches = get_close_matches(s0, names, n=1, cutoff=cutoff)
    if matches:
        return matches[0]
    # fallback: if key allows "другое", return "другое"
    if "другое" in choices:
        return "другое"
    return ""

def safe_string_for_sheet(s: Optional[str], max_len: int = 1000) -> str:
    s2 = norm_text(s)
    if len(s2) > max_len:
        return s2[:max_len]
    return s2

# --- Row normalizer ---
def normalize_offline_row(row: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Input: raw row dict (keys as in your sheet).
    Output: (clean_row, notes) where clean_row is suitable for append_offline_row.
    """
    notes: List[str] = []
    # start with shallow copy
    out = {}

    # Keep raw transcription as-is (but normalized whitespace)
    out["Transcription_raw"] = safe_string_for_sheet(row.get("Transcription_raw", ""))

    # Date / Time pass-through (assume already correct)
    out["Date"] = row.get("Date", "")
    out["Time"] = row.get("Time", "")

    # Client id: keep only last 6 digits if present
    cid = norm_text(row.get("Client_ID", ""))
    if cid:
        digits = "".join(_phone_digits.findall(cid))
        out["Client_ID"] = digits[-6:] if digits else cid
    else:
        out["Client_ID"] = ""

    # Enums
    out["Type_of_client"] = match_enum(row.get("Type_of_client", ""), "Type_of_client")
    if out["Type_of_client"] == "":
        notes.append("Type_of_client not mapped")

    out["Behavior"] = match_enum(row.get("Behavior", ""), "Behavior")
    if out["Behavior"] == "":
        notes.append("Behavior not mapped")

    out["Purchase_status"] = match_enum(row.get("Purchase_status", ""), "Purchase_status")
    if out["Purchase_status"] == "":
        notes.append("Purchase_status not mapped")

    # Numeric fields
    ticket = parse_number(row.get("Ticket_amount"))
    if ticket is None and str(row.get("Ticket_amount", "")).strip() != "":
        notes.append("Ticket_amount parse fail")
    out["Ticket_amount"] = ticket if ticket is not None else ""

    cost = parse_number(row.get("Cost_Price"))
    if cost is None and str(row.get("Cost_Price", "")).strip() != "":
        notes.append("Cost_Price parse fail")
    out["Cost_Price"] = cost if cost is not None else ""

    # Quantity: prefer int if integer-ish
    qty_num = parse_number(row.get("Quantity"))
    if qty_num is not None:
        # if it's effectively integer, store as int
        if abs(qty_num - round(qty_num)) < 1e-9:
            out["Quantity"] = int(round(qty_num))
        else:
            out["Quantity"] = round(qty_num, 3)
    else:
        out["Quantity"] = ""  # allow empty quantity

    # Reason and Source map
    out["Reason_not_buying"] = match_enum(row.get("Reason_not_buying", ""), "Reason_not_buying")
    if out["Reason_not_buying"] == "":
        # if user typed free text, keep sanitized short version
        rn_raw = norm_text(row.get("Reason_not_buying", ""))
        out["Reason_not_buying"] = rn_raw[:100] if rn_raw else ""
        if rn_raw:
            notes.append("Reason_not_buying free text")

    out["Source"] = match_enum(row.get("Source", ""), "Source")
    if out["Source"] == "":
        s_raw = norm_text(row.get("Source", ""))
        out["Source"] = s_raw[:50] if s_raw else ""
        if s_raw:
            notes.append("Source free text")

    # Product / Short note: sanitize
    out["Product_name"] = safe_string_for_sheet(row.get("Product_name", ""), max_len=200)
    out["Short_note"] = safe_string_for_sheet(row.get("Short_note", ""), max_len=1000)

    # Contact
    out["Contact_left"] = match_enum(row.get("Contact_left", ""), "YesNo") or ""
    contact_raw = row.get("Contact", "") or row.get("Contact_left_raw", "")
    out["Contact"] = norm_text(contact_raw)
    phone = norm_phone(contact_raw)
    if phone:
        out["Contact_phone_normalized"] = phone

    # keep Repeat_visit as yes/no normalized
    out["Repeat_visit"] = match_enum(row.get("Repeat_visit", ""), "YesNo") or ""

    # Attach validation notes summary
    out["Validation_note"] = "; ".join(notes)

    return out, notes
