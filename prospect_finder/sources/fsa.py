"""Food Standards Agency hygiene-rating register (free, no key).

Gives an almost complete list of food businesses (cafés, pubs, restaurants,
hotels, B&Bs, takeaways, food shops) with address and coordinates. It has no
website or email, but phone is sometimes present.
"""
from __future__ import annotations

import math
import time

import requests

from .. import config

# FSA business type -> (sector, category). Types mapped to None are skipped:
# they are public bodies or supermarkets, not prospects.
TYPE_MAP = {
    "Restaurant/Cafe/Canteen": ("Hospitality", "Restaurant / café"),
    "Pub/bar/nightclub": ("Hospitality", "Pub / bar"),
    "Hotel/bed & breakfast/guest house": ("Hospitality", "Hotel / B&B"),
    "Takeaway/sandwich shop": ("Hospitality", "Takeaway"),
    "Mobile caterer": ("Hospitality", "Mobile caterer"),
    "Other catering premises": ("Hospitality", "Other catering"),
    "Retailers - other": ("Retail", "Food & drink shop"),
    "Manufacturers/packers": ("Food production", "Food producer"),
    "Farmers/growers": ("Food production", "Farm"),
    "Retailers - supermarkets/hypermarkets": None,
    "School/college/university": None,
    "Hospitals/Childcare/Caring Premises": None,
    "Caring Premises": None,
    "Distributors/Transporters": None,
    "Importers/Exporters": None,
}


def fetch(lat: float, lon: float, radius_km: float, log=print) -> list[dict]:
    # The API misbehaves with fractional distances: ask for whole miles, then trim.
    radius_miles = math.ceil(radius_km / 1.609344)
    headers = {"x-api-version": "2", "Accept": "application/json",
               "User-Agent": config.USER_AGENT}
    out: list[dict] = []
    page = 1
    while True:
        params = {"latitude": lat, "longitude": lon,
                  "maxDistanceLimit": radius_miles,
                  "pageSize": 1000, "pageNumber": page}
        for attempt in range(4):
            try:
                r = requests.get(config.FSA_URL, params=params, headers=headers, timeout=60)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:  # noqa: BLE001
                log(f"  FSA page {page} failed ({e}); retrying")
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError("FSA API unreachable")
        rows = data.get("establishments", [])
        out.extend(rows)
        meta = data.get("meta", {})
        log(f"  FSA page {page}/{meta.get('totalPages')} – {len(out)} of {meta.get('totalCount')}")
        if page >= (meta.get("totalPages") or 1) or not rows:
            break
        page += 1
    from ..geo import haversine_km
    return [b for b in (_normalise(e) for e in out)
            if b and haversine_km(lat, lon, b["lat"], b["lon"]) <= radius_km]


def _normalise(e: dict) -> dict | None:
    mapped = TYPE_MAP.get(e.get("BusinessType"), ("Other", e.get("BusinessType") or ""))
    if mapped is None:
        return None
    geo = e.get("geocode") or {}
    try:
        lat, lon = float(geo["latitude"]), float(geo["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    addr = ", ".join(x for x in (e.get(f"AddressLine{i}") for i in range(1, 5)) if x)
    town = e.get("AddressLine3") or e.get("AddressLine4") or e.get("AddressLine2") or ""
    return {
        "name": (e.get("BusinessName") or "").strip(),
        "sector": mapped[0],
        "category": mapped[1],
        "lat": lat, "lon": lon,
        "address": addr, "postcode": e.get("PostCode") or "", "town": town.strip(),
        "phone": (e.get("Phone") or "").strip(),
        "website": "", "email": "", "socials": {},
        "sources": ["FSA"],
        "fsa_id": e.get("FHRSID"),
        "fsa_rating": e.get("RatingValue"),
        "fsa_rating_date": (e.get("RatingDate") or "")[:10],
        "authority": e.get("LocalAuthorityName") or "",
        "brand": "", "osm_tags": {},
    }
