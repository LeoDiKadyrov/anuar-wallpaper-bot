# app/services/stt.py
import chunk
import os
import wave
import json
from pydub import AudioSegment
from typing import Optional

STT_BACKEND = os.getenv("STT_BACKEND", "vosk")

# Default path to bundled Vosk model (can be overridden via env)
BASE_DIR = os.path.dirname(__file__)
DEFAULT_VOSK_MODEL_PATH = os.path.join(BASE_DIR, "models", "vosk-model-small-ru-0.22")

# ---- VOSK offline backend ----
def vosk_transcribe(filepath: str, model_path: Optional[str] = None) -> str:
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
    try: 
        sound = AudioSegment.from_file(filepath)
        print("DEBUG: original: channels=", sound.channels, "frame_rate=", sound.frame_rate, "duration_s=", len(sound)/1000.0, "sample_width=", sound.sample_width)
    except Exception as e:
        raise RuntimeError("pydub failed to read input: " + str(e))

    sound = sound.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    wav_path = filepath + ".conv.wav"
    debug_copy = os.path.join(os.getcwd(), "debug_last.wav")
    
    try:
        sound.export(wav_path, format="wav")
        sound.export(debug_copy, format="wav")
    except Exception as e:
        raise RuntimeError("Failed to export wav: " + str(e))


    try:
        wf = wave.open(wav_path, "rb")
        params = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes())
        duration = wf.getnframes() / wf.getframerate() if wf.getframerate() else 0
        print(f"DEBUG: converted wav: channels={params[0]}, sampwidth={params[1]}, framerate={params[2]}, nframes={params[3]}, duration_s={duration:.3f}")
    except Exception as e:
        raise RuntimeError("Failed to open converted wav: " + str(e))  

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Vosk model not found at {model_path}. Download and extract it there.")
    print("DEBUG: Using Vosk model at", model_path)

    model = Model(model_path)
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)

    result_texts = []
    wf.rewind()
    chunk_i = 0
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        chunk_i += 1
        if rec.AcceptWaveform(data):
            res = rec.Result()
            # res is JSON string; simple extraction
            try:
                t = json.loads(res).get("text", "")
            except:
                t = ""
            if t: 
                print(f"DEBUG: chunk {chunk_i} final ->", repr(t))
                result_texts.append(t)
        else:
            try:
                part = json.loads(rec.PartialResult()).get("partial", "")
                if part:
                    print(f"DEBUG: chunk {chunk_i} partial ->", repr(part))
            except:
                pass
    # final partial
    final = rec.FinalResult()
    try:
        t = json.loads(final).get("text", "")
        if t:
            print("DEBUG: final result ->", repr(t))
            result_texts.append(t)
    except Exception as e:
        print("DEBUG: failed parse final: ", e)

    wf.close()

    full = " ".join([s for s in result_texts if s]).strip()
    print("DEBUG vosk full result: ", repr(full))
    return full

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
    print("DEBUG: transcribe called with", filepath)
    try:
        from pydub import AudioSegment
        s = AudioSegment.from_file(filepath)
        print("DEBUG: pydub read: channels", s.channels, "framerate", s.frame_rate, "duration_s", len(s)/1000.0)
    except Exception as e:
        print("DEBUG: pydub read failed:", e)


    if STT_BACKEND == "vosk":
        # model path can be overridden via env, fallback to bundled default
        model_path = os.getenv("VOSK_MODEL_PATH", DEFAULT_VOSK_MODEL_PATH)
        print("DEBUG: using VOSK model at", model_path)
        result = vosk_transcribe(filepath, model_path=model_path)
        print("DEBUG: vosk result raw:", repr(result))
        return result
    #elif STT_BACKEND == "openai":
       # return openai_transcribe(filepath)
    else:
        raise RuntimeError("Unknown STT_BACKEND: " + STT_BACKEND)
