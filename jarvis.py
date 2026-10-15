"""
JARVIS — Voice command processor + LLM question handler.
"""

import threading
import queue
import time
import re
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
import pyttsx3

voice_events = queue.Queue()

# ============================================================
# AUDIO CONFIG
# ============================================================
DEVICE = 15
DEVICE_RATE = 48000
WHISPER_RATE = 16000
CHUNK_DURATION = 4.0

# ============================================================
# STATE PROVIDER (hand_tracker injects this)
# ============================================================
_state_provider = None

def set_state_provider(fn):
    global _state_provider
    _state_provider = fn

# ============================================================
# INIT
# ============================================================
print("[JARVIS] Loading Whisper model...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
print("[JARVIS] Whisper ready.")

print("[JARVIS] Initializing TTS...")
tts_engine = pyttsx3.init()
tts_engine.setProperty('rate', 185)
tts_engine.setProperty('volume', 0.9)
print("[JARVIS] TTS ready.")

# ============================================================
# INTENT PARSER
# ============================================================
MARKER_TYPES = ["fire", "medical", "police", "hazard"]

QUESTION_WORDS = [
    "where", "what", "how", "which", "why",
    "should i", "recommend", "suggest", "advise",
    "biggest risk", "most danger", "safest", "route",
    "nearest", "closest",
    "describe", "explain", "summarize", "summary",
    "situation", "status", "report", "brief",
    "tell me", "give me", "analyze", "assess",
    "evaluate", "priority", "prioritize"
]


def parse_intent(text):
    t = text.lower().strip()
    t = re.sub(r'\b(please|can you|could you|hey|jarvis|computer)\b', '', t).strip()

    # ==== QUESTION DETECTION (BEFORE commands) ====
    is_question = (
        t.endswith("?") or
        any(qw in t for qw in QUESTION_WORDS)
    )
    if is_question:
        # But don't hijack clear commands
        if not re.search(r'\b(show|drop|zoom|reset|clear|switch|select|change|count)\b', t):
            return {"action": "ASK_QUESTION", "params": {"question": text.strip()}}

    # ==== COMMANDS ====
    if re.search(r'\b(reset|home|center view|overview)\b', t):
        return {"action": "RESET_VIEW", "params": {}}
    if re.search(r'\b(zoom in|closer|move in)\b', t):
        return {"action": "ZOOM_IN", "params": {}}
    if re.search(r'\b(zoom out|further|pull back|move out)\b', t):
        return {"action": "ZOOM_OUT", "params": {}}
    if re.search(r'\b(clear all|delete all|wipe|remove all)\b', t):
        return {"action": "CLEAR_ALL", "params": {}}

    if re.search(r'\b(how many|count|status of)\b', t):
        for m in MARKER_TYPES:
            if m in t:
                return {"action": "COUNT_MARKERS", "params": {"type": m.upper()}}
        return {"action": "COUNT_MARKERS", "params": {}}

    for m in MARKER_TYPES:
        if m in t and re.search(r'\b(show|highlight|display|find)\b', t):
            return {"action": "SHOW_MARKERS", "params": {"type": m.upper()}}

    for m in MARKER_TYPES:
        if m in t and re.search(r'\b(drop|add|mark|place)\b', t):
            return {"action": "DROP_MARKER", "params": {"type": m.upper()}}

    for m in MARKER_TYPES:
        if m in t and re.search(r'\b(select|switch|change to|set)\b', t):
            return {"action": "SET_MARKER_TYPE", "params": {"type": m.upper()}}

    if re.search(r'\b(help|what can you do|commands)\b', t):
        return {"action": "HELP", "params": {}}

    return None


def get_acknowledgment(intent):
    if not intent:
        return None
    a = intent["action"]
    p = intent.get("params", {})

    if a == "RESET_VIEW": return "Resetting view."
    if a == "ZOOM_IN":    return "Zooming in."
    if a == "ZOOM_OUT":   return "Zooming out."
    if a == "CLEAR_ALL":  return "Clearing all markers."
    if a == "SHOW_MARKERS":    return f"Showing {p['type'].lower()} markers."
    if a == "DROP_MARKER":     return f"Dropping {p['type'].lower()} marker."
    if a == "SET_MARKER_TYPE": return f"Marker type set to {p['type'].lower()}."
    if a == "COUNT_MARKERS":
        if "type" in p:
            return f"Counting {p['type'].lower()} markers."
        return "Counting all markers."
    if a == "HELP":
        return ("Commands: show fire markers, drop medical marker, zoom in, "
                "reset view, clear all. Or ask me anything — "
                "where should I send the ambulance, what's the biggest risk.")
    # ASK_QUESTION is handled separately
    return None


# ============================================================
# TTS
# ============================================================
def speak_async(text):
    if not text:
        return
    def _speak():
        try:
            tts_engine.say(text)
            tts_engine.runAndWait()
        except RuntimeError:
            pass
    threading.Thread(target=_speak, daemon=True).start()


# ============================================================
# LLM HANDLER
# ============================================================
def handle_question(question):
    """Called when a question is detected. Uses the LLM with current state."""
    try:
        from llm_engine import ask_question
    except ImportError:
        return "AI reasoning module not found."

    state = _state_provider() if _state_provider else {}
    answer = ask_question(question, state)
    return answer


# ============================================================
# LISTEN LOOP
# ============================================================
def listen_loop():
    print(f"[JARVIS] Voice listener started on device {DEVICE} @ {DEVICE_RATE}Hz")
    print("[JARVIS] Calibrating ambient noise... (stay quiet for 2 seconds)")

    try:
        cal = sd.rec(int(2.0 * DEVICE_RATE), samplerate=DEVICE_RATE,
                     channels=1, dtype='float32', device=DEVICE)
        sd.wait()
        cal = cal.flatten()
        ambient_rms = float(np.sqrt(np.mean(np.square(cal))))
        print(f"[JARVIS] Ambient floor: {ambient_rms:.4f}")
    except Exception as e:
        print(f"[JARVIS] Calibration failed, using 0.02: {e}")
        ambient_rms = 0.02

    speech_threshold = max(0.025, ambient_rms * 1.4)
    print(f"[JARVIS] Speech threshold: {speech_threshold:.4f}")
    print("[JARVIS] Listening...")

    while True:
        try:
            raw = sd.rec(
                int(CHUNK_DURATION * DEVICE_RATE),
                samplerate=DEVICE_RATE,
                channels=1,
                dtype='float32',
                device=DEVICE
            )
            sd.wait()
            raw = raw.flatten()

            n = len(raw)
            core = raw[int(n * 0.2): int(n * 0.8)]
            raw_rms = float(np.sqrt(np.mean(np.square(core))))

            status = "processing" if raw_rms >= speech_threshold else "skip"
            print(f"[JARVIS] (level: {raw_rms:.3f} — {status})", end="\r")

            if not np.isfinite(raw_rms) or raw_rms < speech_threshold:
                continue

            print(f"\n[JARVIS] (level: {raw_rms:.3f} — processing)")

            audio = raw - np.mean(raw)
            peak = float(np.max(np.abs(audio)))
            if peak > 0.001:
                audio = audio / peak * 0.9
            audio = np.clip(audio, -1.0, 1.0)

            if DEVICE_RATE != WHISPER_RATE:
                ratio = WHISPER_RATE / DEVICE_RATE
                new_len = int(len(audio) * ratio)
                audio = np.interp(
                    np.linspace(0, len(audio) - 1, new_len),
                    np.arange(len(audio)),
                    audio
                ).astype(np.float32)

            segments, _ = whisper_model.transcribe(
                audio, language="en", vad_filter=False, beam_size=5,
                condition_on_previous_text=False, no_speech_threshold=0.6,
                temperature=0.0
            )
            text = " ".join(seg.text for seg in segments).strip()

            if not text or len(text) < 3:
                continue

            lowered = text.lower().strip()
            hallucinations = [
                "thank you", "thanks for watching", "subscribe",
                "see you in the next", "i'm sorry", "bye",
                ". . .", "oh", "so", "you"
            ]
            if any(h in lowered for h in hallucinations) and len(lowered) < 25:
                print(f"[JARVIS] (ignored hallucination: \"{text}\")")
                continue
                        # Filter repetitive hallucinations (same phrase repeated 3+ times)
            import re as _re
            repeats = _re.findall(r'(\b\w+\b)(?:\s+\1){2,}', lowered)
            if repeats:
                print(f"[JARVIS] (ignored repetition: \"{text[:40]}\")")
                continue

            # Filter "and X and X" patterns
            if _re.match(r'^(\s*and\s+[\d.]+\s*,?\s*){3,}', lowered):
                print(f"[JARVIS] (ignored repetition: \"{text[:40]}\")")
                continue

            print(f"[JARVIS] Heard: \"{text}\"")

            intent = parse_intent(text)
            if intent:
                intent["raw_text"] = text

                # ===== SPECIAL HANDLING FOR QUESTIONS =====
                if intent["action"] == "ASK_QUESTION":
                    question = intent["params"]["question"]
                    print(f"[JARVIS] Asking LLM: {question}")
                    answer = handle_question(question)
                    print(f"[JARVIS] Answer: {answer}")

                    # Attach the answer to the event
                    intent["response"] = answer
                    voice_events.put(intent)

                    # Speak the answer
                    speak_async(answer)
                else:
                    # Normal command
                    print(f"[JARVIS] Intent: {intent['action']} {intent.get('params', {})}")
                    voice_events.put(intent)
                    ack = get_acknowledgment(intent)
                    if ack:
                        speak_async(ack)
            else:
                print(f"[JARVIS] No intent matched.")

        except Exception as e:
            print(f"\n[JARVIS] Error: {e}")
            time.sleep(0.5)


def start():
    t = threading.Thread(target=listen_loop, daemon=True)
    t.start()