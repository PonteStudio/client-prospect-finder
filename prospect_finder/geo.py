import math

import requests

from . import config


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve_centre(text: str) -> tuple[float, float, str]:
    """Accepts a known town name, 'lat,lon', or any place name (looked up on OpenStreetMap)."""
    t = text.strip()
    if "," in t:
        try:
            a, b = (float(x) for x in t.split(",", 1))
            return a, b, f"{a:.4f},{b:.4f}"
        except ValueError:
            pass
    if t.lower() in config.TOWNS:
        lat, lon = config.TOWNS[t.lower()]
        return lat, lon, t.title()
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": t + ", UK", "format": "json", "limit": 1},
                     headers={"User-Agent": config.USER_AGENT}, timeout=30)
    r.raise_for_status()
    hits = r.json()
    if not hits:
        raise SystemExit(f"Could not find a place called '{text}'. Try 'lat,lon'.")
    return float(hits[0]["lat"]), float(hits[0]["lon"]), t.title()
