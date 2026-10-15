"""
Live earthquake data from USGS — updated every 5 minutes.
No API key required.
"""

import threading
import time
import requests
from datetime import datetime, timedelta

earthquakes = []
earthquakes_lock = threading.Lock()
version = 0
last_update_time = 0

UPDATE_INTERVAL = 300      # 5 minutes
REQUEST_TIMEOUT = 15
MIN_MAGNITUDE = 3.0        # ignore small quakes
DAYS_BACK = 7


def fetch_earthquakes():
    try:
        start_date = (datetime.utcnow() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")
        url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
        params = {
            "format": "geojson",
            "starttime": start_date,
            "minmagnitude": MIN_MAGNITUDE,
            "orderby": "magnitude",
            "limit": 500
        }
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            print(f"[QUAKE] USGS returned {r.status_code}")
            return None

        data = r.json()
        features = data.get("features", [])

        quakes = []
        for f in features:
            try:
                props = f["properties"]
                coords = f["geometry"]["coordinates"]  # [lon, lat, depth]
                quakes.append({
                    "id": f["id"],
                    "lat": float(coords[1]),
                    "lon": float(coords[0]),
                    "depth": float(coords[2]) if coords[2] is not None else 0.0,
                    "magnitude": float(props.get("mag") or 0),
                    "place": props.get("place", ""),
                    "time": int(props.get("time") or 0)
                })
            except (KeyError, TypeError, ValueError):
                continue

        return quakes
    except Exception as e:
        print(f"[QUAKE] Fetch error: {e}")
        return None


def earthquake_loop():
    global earthquakes, last_update_time, version
    print("[QUAKE] Earthquake tracker started. Fetching every 5 minutes.")
    time.sleep(3)

    while True:
        try:
            quakes = fetch_earthquakes()
            if quakes is not None:
                with earthquakes_lock:
                    earthquakes = quakes
                    last_update_time = time.time()
                    version += 1
                print(f"[QUAKE] {len(quakes)} earthquakes tracked (v{version})")
            else:
                print("[QUAKE] Fetch returned no data. Retrying in 60s.")
                time.sleep(60)
        except Exception as e:
            print(f"[QUAKE] Loop error: {e}")

        time.sleep(UPDATE_INTERVAL)


def get_earthquakes():
    with earthquakes_lock:
        return list(earthquakes)


def get_version():
    with earthquakes_lock:
        return version


def start():
    t = threading.Thread(target=earthquake_loop, daemon=True)
    t.start()