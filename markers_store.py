"""
Simple JSON-based persistence for markers.
Python owns the file; browser sends actions via WebSocket.
"""

import json
import os
import threading

STORE_FILE = "session_markers.json"
_lock = threading.Lock()


def load_markers():
    if not os.path.exists(STORE_FILE):
        return []
    try:
        with open(STORE_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as e:
        print(f"[STORE] Load error: {e}")
    return []


def save_markers(markers):
    with _lock:
        try:
            with open(STORE_FILE, "w") as f:
                json.dump(markers, f, indent=2)
        except Exception as e:
            print(f"[STORE] Save error: {e}")


def clear_store():
    with _lock:
        try:
            if os.path.exists(STORE_FILE):
                os.remove(STORE_FILE)
        except Exception as e:
            print(f"[STORE] Clear error: {e}")