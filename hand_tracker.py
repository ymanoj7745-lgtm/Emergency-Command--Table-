import cv2
import mediapipe as mp
import math
import time
import asyncio
import websockets
import json
import threading
from collections import deque

from jarvis import voice_events, start as start_jarvis, set_state_provider
from live_data import get_flights, get_version as get_flights_version, start as start_live_data
from earthquake_data import get_earthquakes, get_version as get_quake_version, start as start_quake_data
from markers_store import load_markers, save_markers, clear_store

latest_data = {
    "gesture": "NONE",
    "x": 0.5,
    "y": 0.5,
    "active": False,
    "pinch_count": 0,
    "fist_count": 0,
    "active_marker_type": "FIRE",
    "active_marker_index": 0,
    "hand_count": 0,
    "hand1_x": 0.5,
    "hand1_y": 0.5,
    "hand2_x": 0.5,
    "hand2_y": 0.5,
    "spread": 0.0,
    "voice_event": {"id": 0, "action": "NONE", "params": {}, "raw_text": ""},
    "flights": [],
    "flights_version": 0,
    "earthquakes": [],
    "earthquakes_version": 0,
    "saved_markers": [],
    "marker_action": None
}
data_lock = threading.Lock()

MARKER_TYPES = ["FIRE", "MEDICAL", "POLICE", "HAZARD"]
current_marker_index = 0

GESTURE_HISTORY_LEN = 4
PINCH_DISTANCE_THRESHOLD = 0.45
FINGER_EXTENDED_THRESHOLD = 55

PINCH_HOLD_MS = 200
PINCH_DEBOUNCE_MS = 500

FIST_HOLD_MS = 600
FIST_DEBOUNCE_MS = 800

gesture_history = deque(maxlen=GESTURE_HISTORY_LEN)

pinch_counter = 0
pinch_state = "RELEASED"
pinch_press_start = 0
last_pinch_time = -100000

fist_counter = 0
fist_state = "RELEASED"
fist_press_start = 0
last_fist_time = -100000

voice_event_counter = 0
last_flights_version = 0
last_quake_version = 0

markers_list = load_markers()
print(f"[STORE] Loaded {len(markers_list)} saved markers from disk")


# ============================================================
# WebSocket Server
# ============================================================
async def ws_handler(websocket):
    print("[WS] client connected")

    async def send_loop():
        while True:
            with data_lock:
                packet = json.dumps(latest_data)
            try:
                await websocket.send(packet)
            except websockets.exceptions.ConnectionClosed:
                break
            await asyncio.sleep(0.033)

    async def recv_loop():
        try:
            async for message in websocket:
                try:
                    msg = json.loads(message)
                    if msg.get("type") == "marker_action":
                        with data_lock:
                            latest_data["marker_action"] = msg["action"]
                        print(f"[WS] Marker action queued: {msg['action'].get('type')}")
                except Exception as e:
                    print(f"[WS] recv parse error: {e}")
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[WS] recv_loop error: {e}")

    try:
        await asyncio.gather(send_loop(), recv_loop())
    except Exception as e:
        print(f"[WS] handler closed: {e}")
    print("[WS] client disconnected")


def start_ws_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def serve():
        async with websockets.serve(
            ws_handler, "localhost", 8765,
            max_queue=1, ping_interval=20, ping_timeout=20
        ):
            await asyncio.Future()

    try:
        loop.run_until_complete(serve())
    except Exception as e:
        print(f"[WS] server stopped: {e}")


threading.Thread(target=start_ws_server, daemon=True).start()

# ============================================================
# Start Background Services
# ============================================================
print("[MAIN] Starting JARVIS voice listener...")
set_state_provider(lambda: latest_data)
start_jarvis()

print("[MAIN] Starting live aircraft fetcher...")
start_live_data()

print("[MAIN] Starting earthquake fetcher...")
start_quake_data()

with data_lock:
    latest_data["saved_markers"] = markers_list

# ============================================================
# MediaPipe Init
# ============================================================
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7,
    max_num_hands=2,
    model_complexity=0
)


def get_distance(lm1, lm2):
    return math.hypot(lm2.x - lm1.x, lm2.y - lm1.y)


def angle_at_joint(p_a, p_b, p_c):
    v1 = (p_b[0] - p_a[0], p_b[1] - p_a[1], p_b[2] - p_a[2])
    v2 = (p_c[0] - p_b[0], p_c[1] - p_b[1], p_c[2] - p_b[2])
    dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
    mag1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
    mag2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
    if mag1 == 0 or mag2 == 0:
        return 180.0
    cos_a = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_a))


def is_finger_extended(landmarks, mcp, pip, tip):
    angle = angle_at_joint(
        (landmarks[mcp].x, landmarks[mcp].y, landmarks[mcp].z),
        (landmarks[pip].x, landmarks[pip].y, landmarks[pip].z),
        (landmarks[tip].x, landmarks[tip].y, landmarks[tip].z)
    )
    return angle < FINGER_EXTENDED_THRESHOLD


def detect_gesture(hand_landmarks):
    landmarks = hand_landmarks.landmark
    wrist = landmarks[0]
    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    index_mcp = landmarks[5]

    hand_size = get_distance(wrist, index_mcp)
    if hand_size == 0:
        return "UNKNOWN"

    index_ext  = is_finger_extended(landmarks, 5, 6, 8)
    middle_ext = is_finger_extended(landmarks, 9, 10, 12)
    ring_ext   = is_finger_extended(landmarks, 13, 14, 16)
    pinky_ext  = is_finger_extended(landmarks, 17, 18, 20)

    extended_count = sum([index_ext, middle_ext, ring_ext, pinky_ext])

    if extended_count == 0:
        return "FIST"
    if extended_count == 4:
        return "OPEN PALM"

    pinch_distance = get_distance(thumb_tip, index_tip) / hand_size
    if pinch_distance < PINCH_DISTANCE_THRESHOLD:
        return "PINCH"

    return "NEUTRAL"


def stable_gesture():
    if len(gesture_history) < GESTURE_HISTORY_LEN:
        return "NONE"
    first = gesture_history[0]
    for g in gesture_history:
        if g != first:
            return "UNSTABLE"
    return first


# ============================================================
# Camera Setup
# ============================================================
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
cap.set(cv2.CAP_PROP_FPS, 60)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

print("=" * 60)
print("EMERGENCY COMMAND TABLE - Python Brain")
print("=" * 60)
print("WebSocket: ws://localhost:8765")
print("Keys: 1=FIRE  2=MEDICAL  3=POLICE  4=HAZARD  R=RESET  q=QUIT")
print("Gestures: PALM=rotate | PINCH=drop | FIST=delete")
print("Voice:    Commands + AI questions (powered by Groq)")
print("Live:     Aircraft (OpenSky) + Earthquakes (USGS)")
print("=" * 60)

# ============================================================
# Main Loop
# ============================================================
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        continue

    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb_frame.flags.writeable = False
    results = hands.process(rgb_frame)

    if results.multi_hand_landmarks:
        hand_positions = []
        raw_gestures = []

        for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            g = detect_gesture(hand_landmarks)
            raw_gestures.append(g)

            wrist = hand_landmarks.landmark[0]
            middle_mcp = hand_landmarks.landmark[9]
            cx = (wrist.x + middle_mcp.x) / 2
            cy = (wrist.y + middle_mcp.y) / 2
            hand_positions.append((cx, cy))

            debug_text = f"H{idx+1}: {g}"
            cv2.putText(frame, debug_text, (10, 25 + idx * 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

        num_hands = len(hand_positions)

        if num_hands >= 2:
            gesture_history.clear()
            pinch_state = "RELEASED"
            fist_state = "RELEASED"

            x1, y1 = hand_positions[0]
            x2, y2 = hand_positions[1]
            spread = math.hypot(x2 - x1, y2 - y1)

            with data_lock:
                latest_data["hand_count"] = 2
                latest_data["hand1_x"] = x1
                latest_data["hand1_y"] = y1
                latest_data["hand2_x"] = x2
                latest_data["hand2_y"] = y2
                latest_data["spread"] = spread
                latest_data["gesture"] = "ZOOM"
                latest_data["x"] = x1
                latest_data["y"] = y1
                latest_data["active"] = False
                latest_data["pinch_count"] = pinch_counter
                latest_data["fist_count"] = fist_counter
                latest_data["active_marker_type"] = MARKER_TYPES[current_marker_index]
                latest_data["active_marker_index"] = current_marker_index

        else:
            x, y = hand_positions[0]
            raw_gesture = raw_gestures[0]
            gesture_history.append(raw_gesture)
            stable_g = stable_gesture()
            if stable_g == "UNSTABLE":
                stable_g = "NEUTRAL"

            now_ms = time.time() * 1000

            if stable_g == "PINCH":
                if pinch_state == "RELEASED":
                    if (now_ms - last_pinch_time) > PINCH_DEBOUNCE_MS:
                        pinch_state = "PRESSING"
                        pinch_press_start = now_ms
                elif pinch_state == "PRESSING":
                    if (now_ms - pinch_press_start) > PINCH_HOLD_MS:
                        pinch_counter += 1
                        last_pinch_time = now_ms
                        pinch_state = "FIRED"
                        print(f"[PINCH] {MARKER_TYPES[current_marker_index]} dropped (count={pinch_counter})")
            else:
                if pinch_state in ("PRESSING", "FIRED"):
                    pinch_state = "RELEASED"

            if stable_g == "FIST":
                if fist_state == "RELEASED":
                    if (now_ms - last_fist_time) > FIST_DEBOUNCE_MS:
                        fist_state = "PRESSING"
                        fist_press_start = now_ms
                elif fist_state == "PRESSING":
                    if (now_ms - fist_press_start) > FIST_HOLD_MS:
                        fist_counter += 1
                        last_fist_time = now_ms
                        fist_state = "FIRED"
                        print(f"[FIST] delete triggered (count={fist_counter})")
            else:
                if fist_state in ("PRESSING", "FIRED"):
                    fist_state = "RELEASED"

            with data_lock:
                latest_data["hand_count"] = 1
                latest_data["hand1_x"] = x
                latest_data["hand1_y"] = y
                latest_data["hand2_x"] = 0
                latest_data["hand2_y"] = 0
                latest_data["spread"] = 0.0
                latest_data["gesture"] = stable_g
                latest_data["x"] = x
                latest_data["y"] = y
                latest_data["active"] = (stable_g == "OPEN PALM")
                latest_data["pinch_count"] = pinch_counter
                latest_data["fist_count"] = fist_counter
                latest_data["active_marker_type"] = MARKER_TYPES[current_marker_index]
                latest_data["active_marker_index"] = current_marker_index

    else:
        gesture_history.clear()
        pinch_state = "RELEASED"
        fist_state = "RELEASED"
        with data_lock:
            latest_data["active"] = False
            latest_data["gesture"] = "NONE"
            latest_data["hand_count"] = 0
            latest_data["pinch_count"] = pinch_counter
            latest_data["fist_count"] = fist_counter
            latest_data["active_marker_type"] = MARKER_TYPES[current_marker_index]
            latest_data["active_marker_index"] = current_marker_index

    # Voice events
    try:
        while not voice_events.empty():
            event = voice_events.get_nowait()
            voice_event_counter += 1
            with data_lock:
                latest_data["voice_event"] = {
                    "id": voice_event_counter,
                    "action": event["action"],
                    "params": event.get("params", {}),
                    "raw_text": event.get("raw_text", ""),
                    "response": event.get("response", "")
                }
            print(f"[MAIN] Voice event #{voice_event_counter}: {event['action']}")
    except Exception as e:
        print(f"[MAIN] Voice event error: {e}")

    # Marker actions
    action = None
    with data_lock:
        if latest_data.get("marker_action"):
            action = latest_data["marker_action"]
            latest_data["marker_action"] = None

    if action:
        a_type = action.get("type")
        if a_type == "add":
            markers_list.append(action["marker"])
            save_markers(markers_list)
            print(f"[STORE] Marker #{action['marker'].get('id')} added. Total: {len(markers_list)}")
        elif a_type == "delete":
            mid = action.get("id")
            markers_list = [m for m in markers_list if m.get("id") != mid]
            save_markers(markers_list)
            print(f"[STORE] Marker #{mid} deleted. Total: {len(markers_list)}")
        elif a_type == "clear":
            markers_list = []
            clear_store()
            print(f"[STORE] All markers cleared")

        with data_lock:
            latest_data["saved_markers"] = markers_list

    # Flights
    cv = get_flights_version()
    if cv != last_flights_version:
        last_flights_version = cv
        flights = get_flights()
        with data_lock:
            latest_data["flights"] = flights
            latest_data["flights_version"] = cv

    # Earthquakes
    qv = get_quake_version()
    if qv != last_quake_version:
        last_quake_version = qv
        quakes = get_earthquakes()
        with data_lock:
            latest_data["earthquakes"] = quakes
            latest_data["earthquakes_version"] = qv

    # Display + keyboard
    cv2.imshow('Hand Tracking - Emergency Command Table', frame)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break
    elif key == ord('1'):
        current_marker_index = 0
        print(f"[KEY] -> {MARKER_TYPES[current_marker_index]}")
    elif key == ord('2'):
        current_marker_index = 1
        print(f"[KEY] -> {MARKER_TYPES[current_marker_index]}")
    elif key == ord('3'):
        current_marker_index = 2
        print(f"[KEY] -> {MARKER_TYPES[current_marker_index]}")
    elif key == ord('4'):
        current_marker_index = 3
        print(f"[KEY] -> {MARKER_TYPES[current_marker_index]}")
    elif key == ord('r') or key == ord('R'):
        voice_event_counter += 1
        with data_lock:
            latest_data["voice_event"] = {
                "id": voice_event_counter,
                "action": "RESET_VIEW",
                "params": {},
                "raw_text": "reset view (key)",
                "response": ""
            }
        print(f"[KEY] -> RESET VIEW")

cap.release()
cv2.destroyAllWindows()