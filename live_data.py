"""
Live data fetcher for Emergency Command Table.
Currently tracks aircraft via OpenSky Network.
Runs in a background thread. Data pulled by hand_tracker.py.
"""

import threading
import time
import requests

# ============================================================
# SHARED STATE
# ============================================================
flights = []
flights_lock = threading.Lock()
last_update_time = 0
version = 0  # increments each successful fetch

UPDATE_INTERVAL = 30  # seconds between fetches
REQUEST_TIMEOUT = 10

# Mumbai bounding box (generous — planes at altitude cover more area)
BBOX = {
    "lamin": 18.5,
    "lomin": 72.65,
    "lamax": 19.15,
    "lomax": 73.10
}

OPENSKY_URL = "https://opensky-network.org/api/states/all"


# ============================================================
# FETCH
# ============================================================
def fetch_flights():
    """Fetch current aircraft positions from OpenSky."""
    try:
        params = {
            "lamin": BBOX["lamin"],
            "lomin": BBOX["lomin"],
            "lamax": BBOX["lamax"],
            "lomax": BBOX["lomax"]
        }
        r = requests.get(OPENSKY_URL, params=params, timeout=REQUEST_TIMEOUT)

        if r.status_code == 429:
            print("[LIVE] OpenSky rate-limited. Backing off.")
            return None
        if r.status_code != 200:
            print(f"[LIVE] OpenSky returned {r.status_code}")
            return None

        data = r.json()
        states = data.get("states") or []

        planes = []
        for s in states:
            try:
                lon = s[5]
                lat = s[6]
                if lon is None or lat is None:
                    continue

                planes.append({
                    "icao24": s[0],
                    "callsign": (s[1] or "").strip() or "——",
                    "country": s[2] or "",
                    "lon": float(lon),
                    "lat": float(lat),
                    "altitude": float(s[7]) if s[7] is not None else 0.0,
                    "velocity": float(s[9]) if s[9] is not None else 0.0,
                    "heading": float(s[10]) if s[10] is not None else 0.0,
                    "on_ground": bool(s[8])
                })
            except (TypeError, ValueError, IndexError):
                continue

        return planes

    except Exception as e:
        print(f"[LIVE] Flight fetch error: {e}")
        return None


# ============================================================
# BACKGROUND LOOP
# ============================================================
def live_data_loop():
    global flights, last_update_time, version
    print("[LIVE] Aircraft tracker started. Fetching every 30s.")

    # Initial fetch
    time.sleep(2)  # let the main app start first

    while True:
        try:
            planes = fetch_flights()
            if planes is not None:
                with flights_lock:
                    flights = planes
                    last_update_time = time.time()
                    version += 1
                print(f"[LIVE] {len(planes)} aircraft tracked (v{version})")
            else:
                print("[LIVE] Fetch returned no data. Retrying in 60s.")
                time.sleep(30)  # extra backoff
        except Exception as e:
            print(f"[LIVE] Loop error: {e}")

        time.sleep(UPDATE_INTERVAL)


# ============================================================
# PUBLIC API
# ============================================================
def get_flights():
    with flights_lock:
        return list(flights)


def get_version():
    with flights_lock:
        return version


def start():
    t = threading.Thread(target=live_data_loop, daemon=True)
    t.start()