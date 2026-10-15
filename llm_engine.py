"""
LLM Engine — sends questions + live map state to Groq.
Requires GROQ_API_KEY environment variable or .env file.
"""

import os

# Try to load from .env file (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

client = None

if GROQ_API_KEY and GROQ_API_KEY.startswith("gsk_"):
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        print(f"[LLM] Groq client ready (key: {GROQ_API_KEY[:12]}...)")
    except ImportError:
        print("[LLM] groq not installed. Run: pip install groq")
    except Exception as e:
        print(f"[LLM] Client init failed: {e}")
else:
    print("[LLM] No valid API key. Set GROQ_API_KEY in .env file.")
    print("[LLM] Get a free key at https://console.groq.com")


# ============================================================
# SYSTEM PROMPT
# ============================================================
SYSTEM_PROMPT = """You are JARVIS, the AI assistant embedded in an emergency command center for Mumbai, India.

You have access to live map state: emergency markers, earthquakes, aircraft, and weather.

Your job:
- Answer questions about the current situation BRIEFLY (1-2 sentences max)
- Recommend actions when asked ("where should I send the ambulance?")
- Highlight risk zones when asked ("what's the biggest risk?")
- Use the actual data given. Never invent markers or events.
- Speak like a calm, professional operations officer, not a chatbot.

Important: Each marker has a real-world location described as "near [Landmark Name] (distance, direction)". When the operator asks "which area" or "where", USE THE LANDMARK NAME — do not mention map coordinates. Say "near Colaba Causeway" or "at Gateway of India", not "(3.0, -1.0)".

Keep answers SHORT. This is being read aloud through a speaker. No bullet points, no markdown."""


# ============================================================
# CONTEXT BUILDER
# ============================================================
def build_context(state):
    """Convert the map state into a text summary for the LLM."""
    from landmarks import describe_marker

    lines = []

    markers = state.get("saved_markers", [])
    if markers:
        lines.append(f"EMERGENCY MARKERS ON MAP ({len(markers)} total):")
        for m in markers[-25:]:
            mtype = m.get("markerType", "UNKNOWN")
            mid = m.get("id", "?")
            city = m.get("city", "mumbai").capitalize()
            description = describe_marker(m)
            lines.append(f"  Marker #{mid} [{mtype}] in {city} — {description}")
    else:
        lines.append("EMERGENCY MARKERS ON MAP: none")

    quakes = state.get("earthquakes", [])
    if quakes:
        top = sorted(quakes, key=lambda q: -q.get("magnitude", 0))[:5]
        lines.append(f"\nRECENT EARTHQUAKES ({len(quakes)} tracked globally, top 5 by magnitude):")
        for q in top:
            mag = q.get("magnitude", 0)
            place = q.get("place", "unknown location")
            lines.append(f"  M{mag:.1f} - {place}")
    else:
        lines.append("\nRECENT EARTHQUAKES: none loaded")

    flights = state.get("flights", [])
    lines.append(f"\nAIRCRAFT IN MUMBAI AIRSPACE: {len(flights)} active flights")

    lines.append(f"\nOPERATOR IS VIEWING: Colaba / Fort area, South Mumbai (~1.3km area)")

    return "\n".join(lines)


# ============================================================
# ASK THE LLM
# ============================================================
def ask_question(question, state):
    """Send a question + state to the LLM. Returns a text answer."""
    if client is None:
        return "AI reasoning is not configured. Add a Groq API key to llm_engine.py."

    context = build_context(state)

    user_message = f"""Live map state:
{context}

Operator question: {question}

Answer as JARVIS:"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.5,
            max_completion_tokens=800,
            top_p=0.9,
            reasoning_effort="low"
        )

        answer = response.choices[0].message.content

        # Handle None content (rare but happens with reasoning models)
        if not answer:
            print("[LLM] Warning: empty content, retrying without reasoning_effort")
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.5,
                max_completion_tokens=400,
                top_p=0.9
            )
            answer = response.choices[0].message.content or "No response from AI."

        answer = answer.strip()
        answer = answer.replace("**", "").replace("##", "")
        answer = answer.replace("JARVIS:", "").strip()

        if answer.startswith('"') and answer.endswith('"'):
            answer = answer[1:-1]

        print(f"[LLM] Q: {question}")
        print(f"[LLM] A: {answer}")
        return answer

    except Exception as e:
        print(f"[LLM] Error: {e}")
        return f"AI service error: {str(e)[:80]}"