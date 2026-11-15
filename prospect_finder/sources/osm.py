"""OpenStreetMap via the Overpass API (free, no key).

Covers businesses in every sector and often includes website, phone, email
and social media links added by local mappers.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time

import requests

from .. import config
from ..geo import haversine_km

AMENITY = ("restaurant|cafe|pub|bar|fast_food|ice_cream|biergarten|nightclub|"
           "dentist|doctors|veterinary|pharmacy|clinic|car_wash|car_rental|"
           "driving_school|events_venue|arts_centre|cinema|theatre|childcare|"
           "kindergarten|studio|marketplace|boat_rental|bicycle_rental")
TOURISM = ("hotel|guest_house|hostel|camp_site|caravan_site|motel|apartment|"
           "chalet|attraction|museum|gallery|theme_park|zoo|wilderness_hut")
LEISURE = ("fitness_centre|sports_centre|golf_course|marina|horse_riding|dance|"
           "escape_game|bowling_alley|water_park|spa|amusement_arcade|trampoline_park")

SKIP_SHOP = {"vacant", "no", "disused"}


def _query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    b = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
    return (
        "[out:json][timeout:90];("
        f'nwr["name"]["shop"]{b};'
        f'nwr["name"]["office"]{b};'
        f'nwr["name"]["craft"]{b};'
        f'nwr["name"]["healthcare"]{b};'
        f'nwr["name"]["amenity"~"^({AMENITY})$"]{b};'
        f'nwr["name"]["tourism"~"^({TOURISM})$"]{b};'
        f'nwr["name"]["leisure"~"^({LEISURE})$"]{b};'
        ");out center tags;"
    )


def _tiles(lat, lon, radius_km, size_km=12.0):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * math.cos(math.radians(lat)))
    s, n, w, e = lat - dlat, lat + dlat, lon - dlon, lon + dlon
    steps = max(1, math.ceil(2 * radius_km / size_km))
    for i in range(steps):
        for j in range(steps):
            ts = s + (n - s) * i / steps
            tn = s + (n - s) * (i + 1) / steps
            tw = w + (e - w) * j / steps
            te = w + (e - w) * (j + 1) / steps
            # skip tiles entirely outside the circle
            clat = min(max(lat, ts), tn)
            clon = min(max(lon, tw), te)
            if haversine_km(lat, lon, clat, clon) <= radius_km:
                yield (ts, tw, tn, te)


def fetch(lat: float, lon: float, radius_km: float, log=print, cache_dir: str | None = None,
          cache_hours: float = 72) -> list[dict]:
    """Downloads in tiles. Finished tiles are cached so an interrupted run can resume."""
    tiles = list(_tiles(lat, lon, radius_km))
    seen: dict[str, dict] = {}
    for idx, bbox in enumerate(tiles, 1):
        q = _query(bbox)
        path = None
        elements = None
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            path = os.path.join(cache_dir, "osm_" + hashlib.sha1(q.encode()).hexdigest()[:12] + ".json")
            if os.path.exists(path) and time.time() - os.path.getmtime(path) < cache_hours * 3600:
                elements = json.load(open(path))
        if elements is None:
            elements = _run(q, log)
            if path and elements is not None:
                json.dump(elements, open(path, "w"))
        elements = elements or []
        for el in elements:
            seen[f"{el['type']}/{el['id']}"] = el
        log(f"  OSM tile {idx}/{len(tiles)} – {len(seen)} places so far")
    out = []
    for key, el in seen.items():
        b = _normalise(key, el)
        if b and haversine_km(lat, lon, b["lat"], b["lon"]) <= radius_km:
            out.append(b)
    return out


def _run(q: str, log) -> list[dict] | None:
    headers = {"User-Agent": config.USER_AGENT}
    for attempt in range(10):
        url = config.OVERPASS_URLS[attempt % len(config.OVERPASS_URLS)]
        try:
            r = requests.post(url, data={"data": q}, headers=headers, timeout=150)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return r.json().get("elements", [])
            log(f"    Overpass {r.status_code} from {url.split('/')[2]}; retrying")
        except Exception as e:  # noqa: BLE001
            log(f"    Overpass error {type(e).__name__} from {url.split('/')[2]}; retrying")
        time.sleep(min(60, 8 * (attempt + 1)))  # public servers are busy: back off
    log("    !! tile skipped after repeated failures (re-run to retry it)")
    return None


def classify(t: dict) -> tuple[str, str] | None:
    am, tour, shop = t.get("amenity"), t.get("tourism"), t.get("shop")
    if shop in SKIP_SHOP:
        return None
    if am in {"restaurant", "cafe", "pub", "bar", "fast_food", "ice_cream", "biergarten", "nightclub"}:
        return "Hospitality", am.replace("_", " ").title()
    if tour in {"hotel", "guest_house", "hostel", "motel", "apartment", "chalet",
                "camp_site", "caravan_site"}:
        return "Hospitality", tour.replace("_", " ").title()
    if tour or am in {"events_venue", "arts_centre", "cinema", "theatre", "boat_rental",
                      "bicycle_rental"} or t.get("leisure"):
        return "Leisure & Attractions", (tour or am or t.get("leisure")).replace("_", " ").title()
    if am in {"dentist", "doctors", "veterinary", "pharmacy", "clinic"} or t.get("healthcare") \
            or shop in {"hairdresser", "beauty", "cosmetics", "massage", "tattoo", "optician",
                        "nutrition_supplements", "hearing_aids"}:
        return "Health & Beauty", (shop or am or t.get("healthcare")).replace("_", " ").title()
    if shop in {"car", "car_repair", "car_parts", "tyres", "motorcycle", "caravan"} \
            or am in {"car_wash", "car_rental", "driving_school"}:
        return "Automotive", (shop or am).replace("_", " ").title()
    if t.get("craft") or shop in {"hardware", "doityourself", "trade", "garden_centre",
                                  "kitchen", "bathroom_furnishing", "flooring", "glaziery",
                                  "electrical", "plumber"}:
        return "Trades & Home", (t.get("craft") or shop).replace("_", " ").title()
    if t.get("office"):
        return "Professional services", t["office"].replace("_", " ").title()
    if shop:
        return "Retail", shop.replace("_", " ").title()
    if am in {"childcare", "kindergarten", "studio", "marketplace"}:
        return "Other", am.title()
    return "Other", ""


def _first(t: dict, *keys: str) -> str:
    for k in keys:
        if t.get(k):
            return t[k].split(";")[0].strip()
    return ""


def _normalise(key: str, el: dict) -> dict | None:
    t = el.get("tags", {})
    if t.get("office") in {"government", "council", "political_party", "religion",
                           "diplomatic", "educational_institution", "ngo", "association",
                           "charity"}:
        return None
    cls = classify(t)
    if not cls:
        return None
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    if lat is None or lon is None:
        return None
    socials = {}
    for net, keys in {
        "facebook": ("contact:facebook", "facebook"),
        "instagram": ("contact:instagram", "instagram"),
        "twitter": ("contact:twitter", "twitter", "contact:x"),
        "tripadvisor": ("contact:tripadvisor", "tripadvisor"),
        "tiktok": ("contact:tiktok",),
    }.items():
        v = _first(t, *keys)
        if v:
            socials[net] = v
    addr = ", ".join(x for x in (
        " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x),
        t.get("addr:city") or t.get("addr:village") or t.get("addr:town"),
    ) if x)
    return {
        "name": t.get("name", "").strip(),
        "sector": cls[0], "category": cls[1],
        "lat": float(lat), "lon": float(lon),
        "address": addr, "postcode": t.get("addr:postcode", ""),
        "town": t.get("addr:city") or t.get("addr:town") or t.get("addr:village") or "",
        "phone": _first(t, "phone", "contact:phone", "contact:mobile"),
        "website": _first(t, "website", "contact:website", "url"),
        "email": _first(t, "email", "contact:email"),
        "socials": socials,
        "sources": ["OSM"],
        "osm_id": key,
        "brand": t.get("brand") or t.get("brand:wikidata") or t.get("operator:wikidata") or "",
        "osm_tags": {k: t[k] for k in ("stars", "rooms", "beds", "opening_hours", "cuisine")
                     if k in t},
    }
