"""
Landmarks — real-world named locations for each city.
Used to enrich marker descriptions with human-readable area names.
"""

import math

# Must match index.html
SCALE_XZ = 0.018

CITY_CENTERS = {
    "mumbai":    {"lat": 18.9265, "lon": 72.8320},
    "delhi":     {"lat": 28.6265, "lon": 77.2250},
    "bangalore": {"lat": 12.9775, "lon": 77.6000},
}

# Real landmarks inside each city bbox
LANDMARKS = {
    "mumbai": [
        {"name": "Gateway of India",         "lat": 18.9220, "lon": 72.8347, "type": "landmark"},
        {"name": "Taj Mahal Palace Hotel",   "lat": 18.9217, "lon": 72.8332, "type": "hotel"},
        {"name": "Colaba Causeway",          "lat": 18.9235, "lon": 72.8317, "type": "market"},
        {"name": "Regal Cinema",             "lat": 18.9246, "lon": 72.8321, "type": "landmark"},
        {"name": "Flora Fountain",           "lat": 18.9322, "lon": 72.8345, "type": "landmark"},
        {"name": "Bombay High Court",        "lat": 18.9310, "lon": 72.8300, "type": "government"},
        {"name": "Sassoon Dock",             "lat": 18.9160, "lon": 72.8278, "type": "port"},
        {"name": "Ballard Estate",           "lat": 18.9345, "lon": 72.8360, "type": "district"},
        {"name": "Naval Dockyard",           "lat": 18.9250, "lon": 72.8400, "type": "military"},
        {"name": "Chhatrapati Shivaji Museum", "lat": 18.9270, "lon": 72.8320, "type": "museum"},
        {"name": "Elphinstone College",      "lat": 18.9280, "lon": 72.8310, "type": "college"},
        {"name": "St. Thomas Cathedral",     "lat": 18.9320, "lon": 72.8340, "type": "church"},
        {"name": "Horniman Circle",          "lat": 18.9315, "lon": 72.8340, "type": "park"},
        {"name": "Afghan Church",            "lat": 18.9190, "lon": 72.8290, "type": "church"},
        {"name": "Maharashtra Police HQ",    "lat": 18.9260, "lon": 72.8320, "type": "government"},
        {"name": "Navy Nagar",               "lat": 18.9210, "lon": 72.8260, "type": "district"},
    ],
    "delhi": [
        {"name": "Rajiv Chowk",              "lat": 28.6328, "lon": 77.2197, "type": "metro"},
        {"name": "Connaught Place",          "lat": 28.6315, "lon": 77.2167, "type": "landmark"},
        {"name": "Janpath Market",           "lat": 28.6230, "lon": 77.2195, "type": "market"},
        {"name": "Barakhamba Road",          "lat": 28.6300, "lon": 77.2270, "type": "metro"},
        {"name": "Mandi House",              "lat": 28.6257, "lon": 77.2345, "type": "metro"},
        {"name": "National Museum",          "lat": 28.6120, "lon": 77.2200, "type": "museum"},
        {"name": "Jantar Mantar",            "lat": 28.6270, "lon": 77.2165, "type": "landmark"},
        {"name": "Palika Bazaar",            "lat": 28.6315, "lon": 77.2167, "type": "market"},
        {"name": "Bengali Market",           "lat": 28.6300, "lon": 77.2350, "type": "market"},
        {"name": "India Gate",               "lat": 28.6129, "lon": 77.2295, "type": "landmark"},
    ],
    "bangalore": [
        {"name": "Vidhana Soudha",           "lat": 12.9794, "lon": 77.5907, "type": "government"},
        {"name": "Cubbon Park",              "lat": 12.9763, "lon": 77.5929, "type": "park"},
        {"name": "MG Road",                  "lat": 12.9756, "lon": 77.6068, "type": "landmark"},
        {"name": "Brigade Road",             "lat": 12.9716, "lon": 77.6073, "type": "landmark"},
        {"name": "Chinnaswamy Stadium",      "lat": 12.9785, "lon": 77.5996, "type": "stadium"},
        {"name": "UB City",                  "lat": 12.9710, "lon": 77.5950, "type": "mall"},
        {"name": "Mayo Hall",                "lat": 12.9740, "lon": 77.6060, "type": "government"},
        {"name": "Raj Bhavan",               "lat": 12.9840, "lon": 77.5890, "type": "government"},
        {"name": "High Court",               "lat": 12.9780, "lon": 77.5870, "type": "government"},
        {"name": "Bowring Hospital",         "lat": 12.9800, "lon": 77.6050, "type": "hospital"},
    ],
}


def xz_to_latlon(x, z, center_lat, center_lon):
    """Convert map coordinates back to real GPS."""
    R = 6371000
    latRad = math.radians(center_lat)
    lon = center_lon + (x / SCALE_XZ) / (R * math.cos(latRad)) * 180 / math.pi
    lat = center_lat - (z / SCALE_XZ) / R * 180 / math.pi
    return lat, lon


def distance_m(lat1, lon1, lat2, lon2):
    """Approximate distance in meters (good enough for ~1km)."""
    dlat = (lat2 - lat1) * 111000
    dlon = (lon2 - lon1) * 111000 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlon * dlon)


def direction_word(lat1, lon1, lat2, lon2):
    """Return compass direction from point 1 to point 2."""
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    angle = math.degrees(math.atan2(dlon, dlat))
    if -22.5 <= angle < 22.5:    return "N"
    if 22.5 <= angle < 67.5:     return "NE"
    if 67.5 <= angle < 112.5:    return "E"
    if 112.5 <= angle < 157.5:   return "SE"
    if angle >= 157.5 or angle < -157.5: return "S"
    if -157.5 <= angle < -112.5: return "SW"
    if -112.5 <= angle < -67.5:  return "W"
    return "NW"


def describe_marker(marker):
    """Return a rich description for a marker, e.g. 'near Colaba Causeway (180m SE)'."""
    city = marker.get("city", "mumbai")
    x = marker.get("x", 0)
    z = marker.get("z", 0)

    center = CITY_CENTERS.get(city, CITY_CENTERS["mumbai"])
    lat, lon = xz_to_latlon(x, z, center["lat"], center["lon"])

    landmarks = LANDMARKS.get(city, [])
    if not landmarks:
        return f"at map ({x:.1f}, {z:.1f})"

    # Find nearest landmark
    best = None
    best_dist = 999999
    for lm in landmarks:
        d = distance_m(lat, lon, lm["lat"], lm["lon"])
        if d < best_dist:
            best_dist = d
            best = lm

    if not best:
        return f"at map ({x:.1f}, {z:.1f})"

    if best_dist < 50:
        return f"at {best['name']}"

    direction = direction_word(best["lat"], best["lon"], lat, lon)
    return f"near {best['name']} ({int(best_dist)}m {direction})"