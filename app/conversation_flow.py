# app/conversation_flow.py
"""
Manages the conversation flow state machine for data collection.
Separates business logic from telegram handlers.
"""
import re
import math
from typing import Dict, Any, Optional
from datetime import datetime

# Conversation states
STATE_TYPE_CLIENT = "type_client"
STATE_BEHAVIOR = "behavior"
STATE_PURCHASE_STATUS = "purchase_status"
STATE_TICKET_AMOUNT = "ticket_amount"
STATE_COST_PRICE = "cost_price"
STATE_PRODUCT_INFO = "product_info"
STATE_REASON_NOT_BUYING = "reason_not_buying"
STATE_CONTACT_LEFT = "contact_left"
STATE_SOURCE = "source"
STATE_SHORT_NOTE = "short_note"
STATE_COMPLETE = "complete"
STATE_FEEDBACK = "feedback"

BTN_REPORT_PROBLEM = "Что-то не так? (Report)"

# Quick keyboards
TYPE_CLIENT_KB = [["новый"], ["повторный"], ["контрактник/мастер"], ["оптовик"]]
BEHAVIOR_KB = [["мимо прошли"], ["поспрашивали"], ["посмотрели"], ["замеряли/считали"]]
STATUS_KB = [["купили"], ["не купили"], ["думают"], ["обмен"]]
YESNO_KB = [["да"], ["нет"]]
REASON_KB = [
    ["дорого"], ["нет дизайна/цвета"], ["нет в наличии"], ["сравнивают"],
    ["зайдут позже"], ["не целевой"], ["не успел обработать"], ["другое"]
]
SOURCE_KB = [["Instagram"], ["2ГИС"], ["рекомендация"], ["вывеска"], ["TikTok"], ["другое"]]


class ConversationState:
    """Tracks current state of data collection conversation."""
    
    def __init__(self, transcription: str, timestamp: datetime):
        self.data: Dict[str, Any] = {
            "Date": timestamp.date().isoformat(),
            "Time": timestamp.time().strftime("%H:%M"),
            "Transcription_raw": transcription,
            "Client_ID": "",
            "Type_of_client": "",
            "Behavior": "",
            "Purchase_status": "",
            "Ticket_amount": "",
            "Cost_Price": "",
            "Source": "",
            "Reason_not_buying": "",
            "Product_name": "",
            "Quantity": "",
            "Repeat_visit": "",
            "Contact_left": "",
            "Short_note": "",
        }
        self.current_state = STATE_TYPE_CLIENT
    
    def is_complete(self) -> bool:
        """Check if conversation is complete."""
        return self.current_state == STATE_COMPLETE
    
    def get_next_question(self) -> Optional[tuple[str, Any]]:
        """
        Returns (question_text, keyboard) for the next state.
        Returns None if conversation is complete.
        """
        if self.current_state == STATE_TYPE_CLIENT:
            return ("Выбери баля Type_of_client", TYPE_CLIENT_KB)
        
        elif self.current_state == STATE_BEHAVIOR:
            return ("Че он делал? Behavior", BEHAVIOR_KB)
        
        elif self.current_state == STATE_PURCHASE_STATUS:
            return ("Купил или не купил? Purchase status?", STATUS_KB)
        
        elif self.current_state == STATE_TICKET_AMOUNT:
            return ("Че там брат насколько наторговал? Если не знаешь отправляй 0, если знаешь отправляй сумму", None)
        
        elif self.current_state == STATE_COST_PRICE:
            return ("Че там брат СЕБЕСТОИМОСТЬ? Если не знаешь отправляй 0, если знаешь отправляй сумму", None)
        
        elif self.current_state == STATE_PRODUCT_INFO:
            return ("Что именно продали и в каком количестве? Например: 'флизелиновые обои, 3 рулона'", None)
        
        elif self.current_state == STATE_REASON_NOT_BUYING:
            return ("А че не купили? Почему? Отправляй пункты из списка или напиши коротко", REASON_KB)
        
        elif self.current_state == STATE_CONTACT_LEFT:
            return ("Хотя бы контакт оставил? (да/нет)", YESNO_KB)
        
        elif self.current_state == STATE_SOURCE:
            return ("Откуда он узнал про наш секретный бутик обоев? (Source)", SOURCE_KB)
        
        elif self.current_state == STATE_SHORT_NOTE:
            return ("Ну в кратце расскажи что-то еще, а если нечего то /skip", None)
            
        # [NEW] Feedback State
        elif self.current_state == STATE_FEEDBACK:
            return ("Опиши, что пошло не так? Я передам админу:", None)
        
        return None
    
    def process_answer(self, answer: str) -> Optional[str]:
        if self.current_state == STATE_FEEDBACK:
            # We don't save this to the main 'data' dict usually, 
            # but we return it so the bot handler can log it.
            # We return None (no error) and let the bot handler manage the logic.
            return None
        """
        Process user's answer and move to next state.
        Returns error message if validation fails, None if OK.
        """
        import re
        
        answer = answer.strip()
        
        if self.current_state == STATE_TYPE_CLIENT:
            self.data["Type_of_client"] = answer
            self.current_state = STATE_BEHAVIOR
        
        elif self.current_state == STATE_BEHAVIOR:
            self.data["Behavior"] = answer
            self.current_state = STATE_PURCHASE_STATUS
        
        elif self.current_state == STATE_PURCHASE_STATUS:
            self.data["Purchase_status"] = answer
            # Branch: did they buy or not?
            if answer.lower().strip() == "купили":
                self.current_state = STATE_TICKET_AMOUNT
            else:
                self.current_state = STATE_REASON_NOT_BUYING
        
        elif self.current_state == STATE_TICKET_AMOUNT:
            # Parse number with strict validation
            num = self._parse_number(answer)
            if num is None:
                return (
                    "❌ Не могу распарсить сумму чека.\n\n"
                    "✅ Примеры правильного ввода:\n"
                    "• 15000\n"
                    "• 15 000\n"
                    "• 15000.50\n"
                    "• 15,5 тыс\n\n"
                    "❌ НЕ используй:\n"
                    "• Спецсимволы: +, -, *, /, №, ( )\n"
                    "• Текст: 'пятнадцать тысяч'\n"
                    "• Несколько чисел: '15 и 20'\n\n"
                    "Отправь просто число:"
                )
            if num < 0:
                return "❌ Сумма не может быть отрицательной. Отправь положительное число или 0:"
            
            self.data["Ticket_amount"] = num
            self.current_state = STATE_COST_PRICE
        
        elif self.current_state == STATE_COST_PRICE:
            num = self._parse_number(answer)
            if num is None:
                return (
                    "❌ Не могу распарсить себестоимость.\n\n"
                    "✅ Примеры правильного ввода:\n"
                    "• 8000\n"
                    "• 8 000\n"
                    "• 8000.50\n"
                    "• 0 (если не знаешь)\n\n"
                    "Отправь просто число:"
                )
            if num < 0:
                return "❌ Себестоимость не может быть отрицательной. Отправь число >= 0:"
            
            self.data["Cost_Price"] = num
            self.current_state = STATE_SOURCE
        
        elif self.current_state == STATE_PRODUCT_INFO:
            # Extract product name and quantity
            m = re.search(r"(\d+(?:[.,]\d+)?)", answer)
            if m:
                qty = m.group(0).replace(",", ".")
                product_name = (answer[:m.start()] + answer[m.end():]).strip(" ,.-")
            else:
                qty = ""
                product_name = answer
            
            self.data["Product_name"] = product_name
            self.data["Quantity"] = qty
            self.current_state = STATE_SHORT_NOTE
        
        elif self.current_state == STATE_REASON_NOT_BUYING:
            self.data["Reason_not_buying"] = answer
            self.current_state = STATE_CONTACT_LEFT
        
        elif self.current_state == STATE_CONTACT_LEFT:
            self.data["Contact_left"] = answer
            self.current_state = STATE_SOURCE
        
        elif self.current_state == STATE_SOURCE:
            self.data["Source"] = answer
            # If they bought, ask for product details
            if self.data.get("Purchase_status", "").lower().strip() == "купили":
                self.current_state = STATE_PRODUCT_INFO
            else:
                self.current_state = STATE_SHORT_NOTE
        
        elif self.current_state == STATE_SHORT_NOTE:
            self.data["Short_note"] = answer
            self.current_state = STATE_COMPLETE
        
        return None
        
    
    def skip_short_note(self):
        """Skip the short note and complete."""
        if self.current_state == STATE_SHORT_NOTE:
            self.data["Short_note"] = ""
            self.current_state = STATE_COMPLETE
    
    def _parse_number(self, s: str) -> Optional[float]:
        """
        Parse number from string with STRICT validation.
        Only accepts clean numbers, not random text with digits.
        
        Valid: "15000", "15 000", "1 000 000", "15000.50", "15,5", "15 тг"
        Invalid: "1+5", "1№2", "abc123", "15 и 20", "15 20", "1 2 3 4 5"
        """
        s = s.strip()
        if not s:
            return None
        
        # Remove common currency symbols and units
        s_clean = s
        for currency in ['₸', 'тг', 'руб', 'р', '$', '€', '£']:
            s_clean = s_clean.replace(currency, '')
        
        s_clean = s_clean.strip()
        
        # Check for suspicious spacing patterns
        # Valid: "15 000", "1 000 000" (first part 1-3 digits, rest exactly 3)
        # Invalid: "15 20", "1 2 3 4 5"
        if ' ' in s_clean:
            parts = s_clean.split(' ')
            if len(parts) > 1:
                # First part must be 1-3 digits
                if not parts[0].isdigit() or len(parts[0]) < 1 or len(parts[0]) > 3:
                    return None
                
                # Check middle parts (all except last): must be exactly 3 digits
                for part in parts[1:-1]:
                    if not part.isdigit() or len(part) != 3:
                        return None
                
                # Last part: either exactly 3 digits, OR 3 digits + decimal + digits
                last_part = parts[-1]
                if '.' in last_part or ',' in last_part:
                    # Has decimal separator
                    dec_parts = last_part.replace(',', '.').split('.')
                    if len(dec_parts) != 2:
                        return None
                    int_part, frac_part = dec_parts
                    # Integer part validation depends on number of groups
                    if len(parts) > 2:
                        # Multiple thousand groups - integer part must be exactly 3
                        if not int_part.isdigit() or len(int_part) != 3:
                            return None
                    else:
                        # Only 2 parts - integer part can be 1-3 digits
                        if not int_part.isdigit() or len(int_part) < 1 or len(int_part) > 3:
                            return None
                    # Fractional part must be digits
                    if not frac_part.isdigit():
                        return None
                else:
                    # No decimal - must be exactly 3 digits
                    if not last_part.isdigit() or len(last_part) != 3:
                        return None
        
        # Remove spaces
        s_no_spaces = s_clean.replace(' ', '')
        
        # Strict validation: only digits, optional minus, one dot or comma
        if not re.match(r'^-?\d+([.,]\d+)?$', s_no_spaces):
            return None
        
        # Parse
        s_no_spaces = s_no_spaces.replace(',', '.')
        
        try:
            val = float(s_no_spaces)
            if not math.isfinite(val):
                return None
            return val
        except:
            return None
    
