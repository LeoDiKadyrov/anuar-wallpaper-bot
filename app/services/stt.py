# app/services/stt.py
import os
import wave
from pydub import AudioSegment

STT_BACKEND = os.getenv("STT_BACKEND", "vosk")

# Default path to bundled Vosk model (can be overridden via env)
BASE_DIR = os.path.dirname(__file__)
DEFAULT_VOSK_MODEL_PATH = os.path.join(BASE_DIR, "models", "vosk-model-small-ru-0.22")

# ---- VOSK offline backend ----
def vosk_transcribe(filepath: str, model_path: str | None = None):
    """
    filepath: path to audio file (ogg/oga/ogg/opus/etc). We'll convert to wav 16k mono.
    model_path: local vosk model directory (you must download manually or use bundled one).
    """
    if model_path is None:
        model_path = DEFAULT_VOSK_MODEL_PATH
    try:
        from vosk import Model, KaldiRecognizer
    except Exception as e:
        raise RuntimeError("Vosk not installed or import failed: " + str(e))

    # convert to wav 16k mono
    sound = AudioSegment.from_file(filepath)
    sound = sound.set_frame_rate(16000).set_channels(1)
    wav_path = filepath + ".wav"
    sound.export(wav_path, format="wav")

    wf = wave.open(wav_path, "rb")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Vosk model not found at {model_path}. Download and extract it there.")
    model = Model(model_path)
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)

    result_text = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            res = rec.Result()
            # res is JSON string; simple extraction
            import json
            text = json.loads(res).get("text", "")
            if text:
                result_text.append(text)
    # final partial
    final = rec.FinalResult()
    try:
        import json
        text = json.loads(final).get("text", "")
        if text:
            result_text.append(text)
    except:
        pass

    return " ".join(result_text).strip()

# ---- Optional OpenAI backend (paid) ----
#def openai_transcribe(filepath: str):
 #   import openai, os
  #  openai.api_key = os.getenv("OPENAI_API_KEY")
  #  if not openai.api_key:
  #      raise RuntimeError("OPENAI_API_KEY not set")
    # Convert to acceptable format if needed
   # audio_file = open(filepath, "rb")
    #resp = openai.Audio.transcribe("gpt-4o-transcribe", audio_file)  # example; check API model name
    #return resp.get("text", "")

# ---- Public function ----
def transcribe(filepath: str) -> str:
    if STT_BACKEND == "vosk":
        # model path can be overridden via env, fallback to bundled default
        model_path = os.getenv("VOSK_MODEL_PATH", DEFAULT_VOSK_MODEL_PATH)
        return vosk_transcribe(filepath, model_path=model_path)
    elif STT_BACKEND == "openai":
        return openai_transcribe(filepath)
    else:
        raise RuntimeError("Unknown STT_BACKEND: " + STT_BACKEND)
