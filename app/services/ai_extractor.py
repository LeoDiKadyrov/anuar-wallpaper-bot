# app/services/ai_extractor.py
import os
import json
import random
import time
import logging
from google import genai
from google.genai import types
from app.services.validator import ALLOWED

logger = logging.getLogger(__name__)

def extract_data_with_gemini(transcription_text: str):
    """
    Sends transcription to Gemini to extract structured JSON data.
    Includes auto-retry for 429 (Rate Limit) errors.
    Returns dict with extracted fields or empty dict on failure.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("❌ CRITICAL ERROR: GOOGLE_API_KEY not found.")
        return {}

    client = genai.Client(api_key=api_key)

    # Use the stable free-tier model
    MODEL_ID = 'gemini-2.5-flash-lite' 

    # Improved prompt in Russian for better understanding of colloquial speech
    prompt = f"""Ты помощник по внесению данных для магазина обоев.

Проанализируй текст разговора с клиентом и заполни JSON со следующими полями:

- Type_of_client: ОДНО значение ИЗ СПИСКА {ALLOWED['Type_of_client']} или null.
- Behavior: ОДНО значение ИЗ СПИСКА {ALLOWED['Behavior']} или null.
- Purchase_status: ОДНО значение ИЗ СПИСКА {ALLOWED['Purchase_status']} или null.
- Reason_not_buying: ОДНО значение ИЗ СПИСКА {ALLOWED['Reason_not_buying']} или null.
- Source: ОДНО значение ИЗ СПИСКА {ALLOWED['Source']} или null.
- Ticket_amount: число (сумма чека в тенге) или null.
- Cost_Price: число (себестоимость в тенге) или null.
- Product_name: что именно продали (текст) или null.
- Quantity: количество (число) или null.

Важно:
- НЕ придумывай значения. ЕСЛИ ТЫ НЕ УВЕРЕН или информация явно не сказана — ставь null.
- Если в тексте есть фразы про покупку (например, «оптовик купила обоев на пятьдесят тысяч»), тогда:
  - Purchase_status = "купили"
  - Type_of_client = подходящее значение из списка (например, "оптовик")
  - Ticket_amount = соответствующее число (например, 50000)
- Если есть слова про себестоимость («себестоимость двадцать тысяч тенге»), то это Cost_Price.
- Если покупка не состоялась, а есть причина, выбери подходящую Reason_not_buying, иначе null.
- Не добавляй никаких других полей, только перечисленные.

Текст транскрипции (на русском/казахском разговорном языке):
\"\"\"{transcription_text}\"\"\"

Верни ТОЛЬКО один JSON без комментариев, без пояснений, строго в формате:

{{
  "Type_of_client": ...,
  "Behavior": ...,
  "Purchase_status": ...,
  "Ticket_amount": ...,
  "Cost_Price": ...,
  "Source": ...,
  "Reason_not_buying": ...,
  "Product_name": ...,
  "Quantity": ...
}}
"""

    # RETRY LOGIC (Max 3 attempts)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json'
                )
            )
            
            # Parse JSON response
            extracted = json.loads(response.text)
            
            # Debug logging: show what Gemini extracted
            logger.info(f"✅ Gemini extracted: {json.dumps(extracted, ensure_ascii=False, indent=2)}")
            
            return extracted

        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse JSON from Gemini: {e}")
            logger.error(f"Raw response: {response.text if 'response' in locals() else 'No response'}")
            # Don't retry on JSON errors - likely prompt/model issue
            return {}
            
        except Exception as e:
            error_str = str(e)
            # Check if it's a Rate Limit error (429)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait_time = (2 ** attempt) + random.uniform(0, 1)  # Backoff: 1s, 2s, 4s...
                logger.warning(f"⚠️ Quota hit. Retrying in {wait_time:.1f}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                # If it's another error (like Auth or 500), stop immediately
                logger.error(f"❌ AI Error: {e}")
                return {}

    logger.error("❌ Failed after max retries.")
    return {} 