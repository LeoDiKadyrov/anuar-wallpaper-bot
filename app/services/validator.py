# app/services/validator.py
import re
from typing import Tuple, Dict, Any, List, Optional
from difflib import get_close_matches
import math

# --- CONFIG: allowed lists ---
ALLOWED = {
    "Type_of_client": ["новый", "повторный", "контрактник/мастер", "оптовик"],
    "Behavior": ["мимо прошли", "поспрашивали", "посмотрели", "замеряли/считали"],
    "Purchase_status": ["купили", "не купили", "думают", "обмен"],
    "Reason_not_buying": ["дорого", "нет дизайна/цвета", "нет в наличии", "сравнивают",
                         "зайдут позже", "не целевой", "не успел обработать", "другое"],
    "Source": ["Instagram", "2ГИС", "рекомендация", "вывеска", "TikTok", "другое"],
    "YesNo": ["да", "нет"]
}

# Sheet column order (adjust to match your actual sheet!)
SHEET_COLUMNS = [
    "Date", "Time", "Client_ID", "Type_of_client", "Behavior", "Purchase_status",
    "Ticket_amount", "Cost_Price", "Source", "Reason_not_buying", "Product_name",
    "Quantity", "Transcription_raw", "Repeat_visit", "Contact_left", "Short_note"
]

# --- Helpers ---
_digits_re = re.compile(r"\d+([.,]\d+)?")
_phone_digits = re.compile(r"\d+")

def norm_text(s: Optional[str]) -> str:
    """Normalize text: strip, collapse whitespace, remove dangerous chars."""
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\x20-\x7E\u0400-\u04FFА-Яа-яёЁ–—…,-.:()/%]+", "", s)
    return s.strip()

def parse_number(s: Optional[str]) -> Optional[float]:
    """
    Parse a number from string with STRICT validation.
    Rejects strings with invalid characters or multiple numbers.
    
    Valid examples:
      "15000" -> 15000.0
      "15 000" -> 15000.0 (space as thousands separator)
      "1 000 000" -> 1000000.0
      "15000.50" -> 15000.5
      "15,5" -> 15.5
      "15000 тг" -> 15000.0 (currency removed)
      "-100" -> -100.0
    
    Invalid examples (returns None):
      "1+5" -> None (contains +)
      "1№2" -> None (contains №)
      "abc123" -> None (contains letters)
      "15 и 20" -> None (multiple numbers)
      "1.2.3" -> None (multiple dots)
      "15 20" -> None (suspicious: 2 parts but second isn't 3 digits)
      "1 2 3 4 5" -> None (parts aren't proper thousands groups)
    """
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    
    # Remove common currency symbols and units
    s_clean = s
    for currency in ['₸', 'тг', 'руб', 'рублей', 'р', '$', '€', '£', 'тенге']:
        s_clean = s_clean.replace(currency, '')
    
    s_clean = s_clean.strip()
    
    # Check for suspicious spacing patterns before removing spaces
    # Valid thousands separator: first part 1-3 digits, rest exactly 3 digits each
    # "15 000" ✓, "1 000 000" ✓, "15 000.50" ✓, "15 20" ✗, "1 2 3 4 5" ✗
    if ' ' in s_clean:
        parts = s_clean.split(' ')
        if len(parts) > 1:
            # First part can be 1-3 digits
            if not parts[0].isdigit() or len(parts[0]) < 1 or len(parts[0]) > 3:
                return None
            
            # Check middle parts (all except last): must be exactly 3 digits
            for part in parts[1:-1]:
                if not part.isdigit() or len(part) != 3:
                    return None
            
            # Last part: either exactly 3 digits, OR 3 digits + decimal separator + digits
            last_part = parts[-1]
            if '.' in last_part or ',' in last_part:
                # Has decimal separator
                # Split by it (normalize comma to dot first)
                dec_parts = last_part.replace(',', '.').split('.')
                if len(dec_parts) != 2:
                    return None
                int_part, frac_part = dec_parts
                # Integer part should be exactly 3 digits if there are multiple thousand groups
                if len(parts) > 2:
                    if not int_part.isdigit() or len(int_part) != 3:
                        return None
                else:
                    # Only 2 parts total (e.g., "15 000.50")
                    # Integer part can be 1-3 digits
                    if not int_part.isdigit() or len(int_part) < 1 or len(int_part) > 3:
                        return None
                # Fractional part must be digits
                if not frac_part.isdigit():
                    return None
            else:
                # No decimal separator - must be exactly 3 digits
                if not last_part.isdigit() or len(last_part) != 3:
                    return None
    
    # Remove spaces (used as thousands separator in Russian format: 15 000)
    s_no_spaces = s_clean.replace(' ', '')
    
    # STRICT validation: only allow digits, optional minus, and ONE dot or comma
    # Pattern: optional minus, digits, optional (dot/comma + digits)
    if not re.match(r'^-?\d+([.,]\d+)?$', s_no_spaces):
        # Contains invalid characters or wrong format
        return None
    
    # Safe to parse now
    s_no_spaces = s_no_spaces.replace(',', '.')
    
    try:
        val = float(s_no_spaces)
        if math.isfinite(val):
            return val
    except Exception:
        return None
    return None

def parse_int(s: Optional[str]) -> Optional[int]:
    """Parse integer from string."""
    f = parse_number(s)
    if f is None:
        return None
    return int(round(f))

def norm_phone(s: Optional[str]) -> str:
    """Extract and normalize phone number."""
    if not s:
        return ""
    digits = "".join(_phone_digits.findall(str(s)))
    # Keep last 9-12 digits
    if len(digits) >= 9:
        return digits[-12:]
    return digits

def match_enum(s: Optional[str], key: str, cutoff: float = 0.6) -> str:
    """
    Map free text to allowed enum value.
    Returns matched value or empty string if no match.
    """
    s0 = norm_text(s).lower()
    if not s0:
        return ""
    
    choices = ALLOWED.get(key, [])
    
    # Exact match (case-insensitive)
    for c in choices:
        if s0 == c.lower():
            return c
    
    # Substring match
    for c in choices:
        if s0 in c.lower() or c.lower() in s0:
            return c
    
    # Fuzzy match
    matches = get_close_matches(s0, [c.lower() for c in choices], n=1, cutoff=cutoff)
    if matches:
        # Find original case version
        for c in choices:
            if c.lower() == matches[0]:
                return c
    
    # Fallback: if "другое" exists, return it for unmatched values
    if "другое" in choices:
        return "другое"
    
    return ""

def safe_string_for_sheet(s: Optional[str], max_len: int = 1000) -> str:
    """Ensure string is safe for Google Sheets."""
    s2 = norm_text(s)
    if len(s2) > max_len:
        return s2[:max_len]
    return s2

def guess_quantity_from_text(text: str) -> str:
    """
    Try to extract a quantity number from free text.
    Returns first number found, or empty string.
    """
    if not text:
        return ""
    m = re.search(r"\d+(?:[.,]\d+)?", text)
    if not m:
        return ""
    return m.group(0).replace(",", ".")

# --- Main validation function ---
def validate_and_normalize_row(row: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Validate and normalize a row before writing to sheet.
    
    Returns:
        (is_valid, normalized_row, error_messages)
        - is_valid: True if row passes all critical validations
        - normalized_row: Cleaned and validated data
        - error_messages: List of validation errors/warnings
    """
    errors: List[str] = []
    warnings: List[str] = []
    out = {}
    
    # --- CRITICAL FIELDS (must be present and valid) ---
    
    # Date/Time
    if not row.get("Date"):
        errors.append("❌ Date is required")
    out["Date"] = row.get("Date", "")
    
    if not row.get("Time"):
        errors.append("❌ Time is required")
    out["Time"] = row.get("Time", "")
    
    # Type_of_client (required)
    type_client = match_enum(row.get("Type_of_client", ""), "Type_of_client")
    if not type_client:
        errors.append("❌ Type_of_client is required and must be valid")
    out["Type_of_client"] = type_client
    
    # Behavior (required)
    behavior = match_enum(row.get("Behavior", ""), "Behavior")
    if not behavior:
        errors.append("❌ Behavior is required and must be valid")
    out["Behavior"] = behavior
    
    # Purchase_status (required)
    purchase_status = match_enum(row.get("Purchase_status", ""), "Purchase_status")
    if not purchase_status:
        errors.append("❌ Purchase_status is required and must be valid")
    out["Purchase_status"] = purchase_status
    
    # --- CONDITIONAL FIELDS (depend on purchase status) ---
    
    if purchase_status == "купили":
        # For purchases: require ticket amount
        ticket = parse_number(row.get("Ticket_amount"))
        if ticket is None or ticket <= 0:
            errors.append("❌ Для покупки нужна сумма чека > 0")
        out["Ticket_amount"] = ticket if ticket is not None else ""
        
        # Cost price is optional but should be validated if present
        cost = parse_number(row.get("Cost_Price"))
        out["Cost_Price"] = cost if cost is not None else ""
        
        # Product name should be present
        product = safe_string_for_sheet(row.get("Product_name", ""), max_len=200)
        if not product:
            warnings.append("⚠️ Product_name желательно указать для покупки")
        out["Product_name"] = product
        
        # Quantity should be present
        qty_num = parse_number(row.get("Quantity"))
        if qty_num is not None:
            if abs(qty_num - round(qty_num)) < 1e-9:
                out["Quantity"] = int(round(qty_num))
            else:
                out["Quantity"] = round(qty_num, 3)
        else:
            out["Quantity"] = ""
            warnings.append("⚠️ Quantity желательно указать для покупки")
        
        # Reason not buying should be empty
        out["Reason_not_buying"] = ""
        
    else:
        # For non-purchases: no ticket/cost/product
        out["Ticket_amount"] = ""
        out["Cost_Price"] = ""
        out["Product_name"] = ""
        out["Quantity"] = ""
        
        # Reason not buying is helpful but not critical
        reason = match_enum(row.get("Reason_not_buying", ""), "Reason_not_buying")
        if not reason:
            # Allow free text
            reason_raw = norm_text(row.get("Reason_not_buying", ""))
            out["Reason_not_buying"] = reason_raw[:100] if reason_raw else ""
        else:
            out["Reason_not_buying"] = reason
    
    # --- OPTIONAL FIELDS ---
    
    # Client ID (last 6 digits)
    cid = norm_text(row.get("Client_ID", ""))
    if cid:
        digits = "".join(_phone_digits.findall(cid))
        out["Client_ID"] = digits[-6:] if digits else cid
    else:
        out["Client_ID"] = ""
    
    # Source
    source = match_enum(row.get("Source", ""), "Source")
    if not source:
        source_raw = norm_text(row.get("Source", ""))
        out["Source"] = source_raw[:50] if source_raw else ""
    else:
        out["Source"] = source
    
    # Contact left
    out["Contact_left"] = match_enum(row.get("Contact_left", ""), "YesNo") or ""
    
    # Repeat visit
    out["Repeat_visit"] = match_enum(row.get("Repeat_visit", ""), "YesNo") or ""
    
    # Short note
    out["Short_note"] = safe_string_for_sheet(row.get("Short_note", ""), max_len=1000)
    
    # Transcription (keep as-is)
    out["Transcription_raw"] = safe_string_for_sheet(row.get("Transcription_raw", ""))
    
    # --- VALIDATION SUMMARY ---
    all_messages = errors + warnings
    is_valid = len(errors) == 0
    
    return is_valid, out, all_messages


def prepare_row_for_sheet(row: Dict[str, Any]) -> List[Any]:
    """
    Convert validated row dict to list in correct column order.
    """
    return [row.get(col, "") for col in SHEET_COLUMNS]