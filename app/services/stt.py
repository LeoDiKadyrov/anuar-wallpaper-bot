# app/services/stt.py
import chunk
import os
import wave
import json
import logging
from pydub import AudioSegment
from typing import Optional

from app.config import STT_BACKEND, VOSK_MODEL_PATH

logger = logging.getLogger(__name__)

#STT_BACKEND = os.getenv("STT_BACKEND", "vosk")

# Default path to bundled Vosk model (can be overridden via env)
#BASE_DIR = os.path.dirname(__file__)
#DEFAULT_VOSK_MODEL_PATH = os.path.join(BASE_DIR, "models", "vosk-model-small-ru-0.22")

# ---- VOSK offline backend ----
def vosk_transcribe(filepath: str, model_path: Optional[str] = None) -> str:
    """
    filepath: path to audio file (ogg/oga/ogg/opus/etc). We'll convert to wav 16k mono.
    model_path: local vosk model directory (you must download manually or use bundled one).
    """
    if model_path is None:
        model_path = VOSK_MODEL_PATH
    try:
        from vosk import Model, KaldiRecognizer
    except Exception as e:
        raise RuntimeError("Vosk not installed or import failed") from e

    # convert to wav 16k mono
    try: 
        sound = AudioSegment.from_file(filepath)
        sound = sound.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        wav_path = filepath + ".conv.wav"
        sound.export(wav_path, format="wav")
    except Exception as e:
        logger.error(f"Audio conversion failed: {e}")
        raise RuntimeError(f"Audio conversion failed: {e}")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Vosk model not found at {model_path}")
        
    logger.info(f"Loading Vosk model from: {model_path}")

    try:
        wf = wave.open(wav_path, "rb")
        model = Model(model_path)
        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)

        result_texts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                if res.get("text"):
                    result_texts.append(res["text"])
        
        final_res = json.loads(rec.FinalResult())
        if final_res.get("text"):
            result_texts.append(final_res["text"])
            
        wf.close()
        
        # Cleanup temp file
        if os.path.exists(wav_path):
            os.remove(wav_path)

        full_text = " ".join(result_texts).strip()
        logger.info(f"Transcription success: {full_text[:50]}...")
        return full_text

    except Exception as e:
        logger.error(f"Vosk transcription error: {e}")
        raise

# ---- Public function ----
def transcribe(filepath: str) -> str:
    logger.info(f"Starting transcription for {filepath} using {STT_BACKEND}")
    
    if STT_BACKEND == "vosk":
        return vosk_transcribe(filepath)
    else:
        raise RuntimeError(f"Unknown STT_BACKEND: {STT_BACKEND}")
