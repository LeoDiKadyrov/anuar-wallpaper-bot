# app/conversation_flow.py
"""
Manages the conversation flow state machine for data collection.
Separates business logic from telegram handlers.
"""
import re
import math
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

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
        report_btn_row = [[BTN_REPORT_PROBLEM]]
        
        if self.current_state == STATE_TYPE_CLIENT:
            # Add report button to the existing list
            return ("Выбери баля Type_of_client", TYPE_CLIENT_KB + report_btn_row)
        
        elif self.current_state == STATE_BEHAVIOR:
            return ("Че он делал? Behavior", BEHAVIOR_KB + report_btn_row)
        
        elif self.current_state == STATE_PURCHASE_STATUS:
            return ("Купил или не купил? Purchase status?", STATUS_KB + report_btn_row)
        
        elif self.current_state == STATE_TICKET_AMOUNT:
            # Currently returns None (which removes keyboard). 
            # If you want the report button here too, return report_btn_row instead of None.
            return ("Че там брат насколько наторговал? Если не знаешь отправляй 0, если знаешь отправляй сумму", report_btn_row)
        
        elif self.current_state == STATE_COST_PRICE:
            return ("Че там брат СЕБЕСТОИМОСТЬ? Если не знаешь отправляй 0, если знаешь отправляй сумму", report_btn_row)
        
        elif self.current_state == STATE_PRODUCT_INFO:
            return ("Что именно продали и в каком количестве? Например: 'флизелиновые обои, 3 рулона'", report_btn_row)
        
        elif self.current_state == STATE_REASON_NOT_BUYING:
            return ("А че не купили? Почему? Отправляй пункты из списка или напиши коротко", REASON_KB + report_btn_row)
        
        elif self.current_state == STATE_CONTACT_LEFT:
            return ("Хотя бы контакт оставил? (да/нет)", YESNO_KB + report_btn_row)
        
        elif self.current_state == STATE_SOURCE:
            return ("Откуда он узнал про наш секретный бутик обоев? (Source)", SOURCE_KB + report_btn_row)
        
        elif self.current_state == STATE_SHORT_NOTE:
            return ("Ну в кратце расскажи что-то еще, а если нечего то /skip", report_btn_row)
            
        elif self.current_state == STATE_FEEDBACK:
            # No report button needed inside the report menu itself
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
        
        # After processing answer, auto-advance through any pre-filled fields
        self._auto_advance_through_filled_fields()
        
        return None
        
    # Add this method inside the ConversationState class

    def _auto_advance_through_filled_fields(self):
        """
        Helper: Automatically advance state machine through fields that are already filled.
        Called after user answers a question to skip over pre-filled fields.
        """
        max_iterations = 15
        for _ in range(max_iterations):
            if self.is_complete():
                break
                
            current_state = self.current_state
            
            # Check if current state's field is already filled, and advance if so
            if current_state == STATE_TYPE_CLIENT:
                if self.data.get("Type_of_client"):
                    self.current_state = STATE_BEHAVIOR
                    continue
                break
                
            elif current_state == STATE_BEHAVIOR:
                if self.data.get("Behavior"):
                    self.current_state = STATE_PURCHASE_STATUS
                    continue
                break
                
            elif current_state == STATE_PURCHASE_STATUS:
                if self.data.get("Purchase_status"):
                    purchase_status = self.data.get("Purchase_status", "").lower().strip()
                    if purchase_status == "купили":
                        self.current_state = STATE_TICKET_AMOUNT
                    else:
                        self.current_state = STATE_REASON_NOT_BUYING
                    continue
                break
                
            elif current_state == STATE_TICKET_AMOUNT:
                if self.data.get("Ticket_amount") is not None or self.data.get("Ticket_amount") == 0:
                    self.current_state = STATE_COST_PRICE
                    continue
                break
                
            elif current_state == STATE_COST_PRICE:
                # Cost_Price can be empty, always advance
                self.current_state = STATE_SOURCE
                continue
                
            elif current_state == STATE_REASON_NOT_BUYING:
                if self.data.get("Reason_not_buying"):
                    self.current_state = STATE_CONTACT_LEFT
                    continue
                break
                
            elif current_state == STATE_CONTACT_LEFT:
                # Contact_left is not auto-filled, stop here
                break
                
            elif current_state == STATE_SOURCE:
                if self.data.get("Source"):
                    purchase_status = self.data.get("Purchase_status", "").lower().strip()
                    if purchase_status == "купили":
                        self.current_state = STATE_PRODUCT_INFO
                    else:
                        self.current_state = STATE_SHORT_NOTE
                    continue
                break
                
            elif current_state == STATE_PRODUCT_INFO:
                if self.data.get("Product_name") or self.data.get("Quantity"):
                    self.current_state = STATE_SHORT_NOTE
                    continue
                break
                
            elif current_state == STATE_SHORT_NOTE:
                # Always stop at short note (user can skip)
                break
                
            else:
                break

    def _advance_state_for_missing_field(self):
        """
        Helper: Advance state machine to next state when current field is missing.
        Respects branching logic (e.g., Purchase_status determines next state).
        """
        if self.current_state == STATE_TYPE_CLIENT:
            self.current_state = STATE_BEHAVIOR
        elif self.current_state == STATE_BEHAVIOR:
            self.current_state = STATE_PURCHASE_STATUS
        elif self.current_state == STATE_PURCHASE_STATUS:
            # Branch based on what we have in data (might be filled already)
            purchase_status = self.data.get("Purchase_status", "").lower().strip()
            if purchase_status == "купили":
                self.current_state = STATE_TICKET_AMOUNT
            else:
                self.current_state = STATE_REASON_NOT_BUYING
        elif self.current_state == STATE_TICKET_AMOUNT:
            self.current_state = STATE_COST_PRICE
        elif self.current_state == STATE_COST_PRICE:
            self.current_state = STATE_SOURCE
        elif self.current_state == STATE_REASON_NOT_BUYING:
            self.current_state = STATE_CONTACT_LEFT
        elif self.current_state == STATE_CONTACT_LEFT:
            self.current_state = STATE_SOURCE
        elif self.current_state == STATE_SOURCE:
            # Branch: if they bought, ask for product info, else short note
            purchase_status = self.data.get("Purchase_status", "").lower().strip()
            if purchase_status == "купили":
                self.current_state = STATE_PRODUCT_INFO
            else:
                self.current_state = STATE_SHORT_NOTE
        elif self.current_state == STATE_PRODUCT_INFO:
            self.current_state = STATE_SHORT_NOTE
        # STATE_SHORT_NOTE and STATE_COMPLETE don't advance further

    def apply_extracted_data(self, extracted: Dict[str, Any]):
        """
        Auto-fills the conversation using data extracted by AI.
        Strategy: Fill all available fields directly, then advance state machine to first missing field.
        """
        if not extracted:
            logger.info("No extracted data to apply")
            return
            
        logger.info(f"Applying extracted data, starting from state: {self.current_state}")
        logger.info(f"Extracted data: {extracted}")
        
        # Step 1: Fill all available fields directly into self.data (bypassing state machine)
        # This allows us to fill fields out of order
        
        # Fill simple fields directly
        if extracted.get("Type_of_client"):
            self.data["Type_of_client"] = extracted["Type_of_client"]
            logger.info(f"Direct-filled Type_of_client: {extracted['Type_of_client']}")
        
        if extracted.get("Behavior"):
            self.data["Behavior"] = extracted["Behavior"]
            logger.info(f"Direct-filled Behavior: {extracted['Behavior']}")
        
        if extracted.get("Purchase_status"):
            self.data["Purchase_status"] = extracted["Purchase_status"]
            logger.info(f"Direct-filled Purchase_status: {extracted['Purchase_status']}")
        
        if extracted.get("Source"):
            self.data["Source"] = extracted["Source"]
            logger.info(f"Direct-filled Source: {extracted['Source']}")
        
        if extracted.get("Reason_not_buying"):
            self.data["Reason_not_buying"] = extracted["Reason_not_buying"]
            logger.info(f"Direct-filled Reason_not_buying: {extracted['Reason_not_buying']}")
        
        # Fill numeric fields (validate first)
        if extracted.get("Ticket_amount") is not None:
            ticket_str = str(extracted["Ticket_amount"])
            ticket_num = self._parse_number(ticket_str)
            if ticket_num is not None and ticket_num >= 0:
                self.data["Ticket_amount"] = ticket_num
                logger.info(f"Direct-filled Ticket_amount: {ticket_num}")
        
        if extracted.get("Cost_Price") is not None:
            cost_str = str(extracted["Cost_Price"])
            cost_num = self._parse_number(cost_str)
            if cost_num is not None and cost_num >= 0:
                self.data["Cost_Price"] = cost_num
                logger.info(f"Direct-filled Cost_Price: {cost_num}")
        
        # Fill product info
        if extracted.get("Product_name"):
            self.data["Product_name"] = extracted["Product_name"]
            logger.info(f"Direct-filled Product_name: {extracted['Product_name']}")
        
        if extracted.get("Quantity") is not None:
            qty_str = str(extracted["Quantity"])
            qty_num = self._parse_number(qty_str)
            if qty_num is not None:
                self.data["Quantity"] = qty_num if abs(qty_num - round(qty_num)) < 1e-9 else round(qty_num, 3)
                logger.info(f"Direct-filled Quantity: {self.data['Quantity']}")
        
        # Step 2: Advance state machine to the first missing field
        # We need to respect the order: Type_of_client -> Behavior -> Purchase_status -> ...
        # and handle branching logic
        
        while not self.is_complete():
            current_state = self.current_state
            
            # Check if current state's field is filled
            if current_state == STATE_TYPE_CLIENT:
                if not self.data.get("Type_of_client"):
                    break  # Stop and ask user
                self.current_state = STATE_BEHAVIOR
                
            elif current_state == STATE_BEHAVIOR:
                if not self.data.get("Behavior"):
                    break  # Stop and ask user
                self.current_state = STATE_PURCHASE_STATUS
                
            elif current_state == STATE_PURCHASE_STATUS:
                if not self.data.get("Purchase_status"):
                    break  # Stop and ask user
                # Branch based on purchase status
                purchase_status = self.data.get("Purchase_status", "").lower().strip()
                if purchase_status == "купили":
                    self.current_state = STATE_TICKET_AMOUNT
                else:
                    self.current_state = STATE_REASON_NOT_BUYING
                    
            elif current_state == STATE_TICKET_AMOUNT:
                if not self.data.get("Ticket_amount") and self.data.get("Ticket_amount") != 0:
                    break  # Stop and ask user
                self.current_state = STATE_COST_PRICE
                
            elif current_state == STATE_COST_PRICE:
                # Cost_Price can be 0 or empty, so we always advance
                self.current_state = STATE_SOURCE
                
            elif current_state == STATE_REASON_NOT_BUYING:
                if not self.data.get("Reason_not_buying"):
                    break  # Stop and ask user
                self.current_state = STATE_CONTACT_LEFT
                
            elif current_state == STATE_CONTACT_LEFT:
                # Contact_left is not extracted by Gemini, so we stop here
                break
                
            elif current_state == STATE_SOURCE:
                if not self.data.get("Source"):
                    break  # Stop and ask user
                # Branch: if they bought, ask for product info, else short note
                purchase_status = self.data.get("Purchase_status", "").lower().strip()
                if purchase_status == "купили":
                    self.current_state = STATE_PRODUCT_INFO
                else:
                    self.current_state = STATE_SHORT_NOTE
                    
            elif current_state == STATE_PRODUCT_INFO:
                # Check if we have product info
                if not self.data.get("Product_name") and not self.data.get("Quantity"):
                    break  # Stop and ask user
                self.current_state = STATE_SHORT_NOTE
                
            elif current_state == STATE_SHORT_NOTE:
                # Short note is optional, always stop here
                break
                
            else:
                # Unknown state, stop
                break
        
        logger.info(f"Auto-fill complete. Current state: {self.current_state}")
    
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
    
