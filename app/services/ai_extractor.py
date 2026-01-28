# app/services/ai_extractor.py
import os
import json
from google import genai
from google.genai import types
from app.services.validator import ALLOWED

def extract_data_with_gemini(transcription_text: str):
    """
    Sends transcription to Gemini to extract structured JSON data.
    Includes auto-retry for 429 (Rate Limit) errors.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ CRITICAL ERROR: GOOGLE_API_KEY not found.")
        return {}

    client = genai.Client(api_key=api_key)

    # Use the stable free-tier model
    MODEL_ID = 'gemini-2.5-flash-lite' 

    prompt = f"""
    You are a data entry assistant for a wallpaper store. 
    Analyze the following sales transcription and extract data into a JSON format.
    
    Transcription: "{transcription_text}"
    
    Match extracted values strictly to these allowed lists:
    - Type_of_client: {ALLOWED['Type_of_client']}
    - Behavior: {ALLOWED['Behavior']}
    - Purchase_status: {ALLOWED['Purchase_status']}
    - Reason_not_buying: {ALLOWED['Reason_not_buying']}
    - Source: {ALLOWED['Source']}
    
    For numeric fields (Ticket_amount, Cost_Price), extract only the number (e.g. 15000).
    For 'Product_name' and 'Quantity', extract what was sold if mentioned.
    
    Return a valid JSON object with keys: 
    Type_of_client, Behavior, Purchase_status, Ticket_amount, Cost_Price, Source, Reason_not_buying, Product_name, Quantity.
    
    If a field is not mentioned, set it to null.
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
            return json.loads(response.text)

        except Exception as e:
            error_str = str(e)
            # Check if it's a Rate Limit error (429)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait_time = (2 ** attempt) + random.uniform(0, 1) # Backoff: 1s, 2s, 4s...
                print(f"⚠️ Quota hit. Retrying in {wait_time:.1f}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                # If it's another error (like Auth or 500), stop immediately
                print(f"❌ AI Error: {e}")
                return {}

    print("❌ Failed after max retries.")
    return {} 