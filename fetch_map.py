import matplotlib
matplotlib.use('Agg')

import osmnx as ox
import json
import math

# Bounding boxes for each city
CITIES = {
    "mumbai": {
        "north": 18.9320, "south": 18.9210,
        "east": 72.8380, "west": 72.8260
    },
    "delhi": {
        "north": 28.6350, "south": 28.6180,
        "east": 77.2350, "west": 77.2150
    },
    "bangalore": {
        "north": 12.9850, "south": 12.9700,
        "east": 77.6100, "west": 77.5900
    },
    "chennai": {
        "north": 13.0750, "south": 13.0580,
        "east": 80.2950, "west": 80.2750
    }
}


def fetch_city(name, bbox):
    print(f"\n{'='*60}")
    print(f"Fetching: {name.upper()}")
    print(f"{'='*60}")

    try:
        buildings = ox.features_from_bbox(
            bbox=(bbox["west"], bbox["south"], bbox["east"], bbox["north"]),
            tags={"building": True}
        )
    except Exception as e:
        print(f"Failed to fetch {name}: {e}")
        return

    print(f"Found {len(buildings)} building footprints.")

    output = []
    skipped = 0

    for idx, row in buildings.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            skipped += 1
            continue
        if geom.geom_type != 'Polygon':
            skipped += 1
            continue

        try:
            coords = list(geom.exterior.coords)
        except Exception:
            skipped += 1
            continue

        polygon = []
        for pt in coords:
            try:
                lat = float(pt[1])
                lon = float(pt[0])
                if math.isfinite(lat) and math.isfinite(lon):
                    polygon.append([lat, lon])
            except Exception:
                continue

        if len(polygon) < 3:
            skipped += 1
            continue

        height = 10.0
        if 'height' in row and row['height'] is not None:
            try:
                h = float(str(row['height']).replace('m', '').strip())
                if math.isfinite(h) and h > 0:
                    height = h
            except Exception:
                pass
        elif 'building:levels' in row and row['building:levels'] is not None:
            try:
                levels = float(row['building:levels'])
                if math.isfinite(levels) and levels > 0:
                    height = levels * 3.2
            except Exception:
                pass

        if not math.isfinite(height):
            height = 10.0
        height = max(3.0, min(height, 150.0))

        output.append({
            "polygon": polygon,
            "height": height
        })

    filename = f"{name}_buildings.json"
    with open(filename, 'w') as f:
        json.dump(output, f, allow_nan=False)

    print(f"✓ Saved {len(output)} buildings to {filename}")
    print(f"  Skipped {skipped} invalid geometries")


for name, bbox in CITIES.items():
    fetch_city(name, bbox)

print(f"\n{'='*60}")
print("ALL CITIES FETCHED")
print(f"{'='*60}")