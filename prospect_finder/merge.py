"""Combine records from different sources, remove duplicates and national chains."""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from .geo import haversine_km

# National / regional chains and franchises: not prospects for a local studio.
CHAINS = [
    "greggs", "costa", "starbucks", "mcdonald", "kfc", "subway", "burger king", "domino",
    "pizza hut", "wetherspoon", "premier inn", "travelodge", "co-op", "coop", "co-operative",
    "tesco", "sainsbury", "asda", "morrisons", "aldi", "lidl", "iceland", "spar", "londis",
    "nisa", "one stop", "budgens", "marks & spencer", "m&s", "boots", "superdrug",
    "holland & barrett", "b&m", "home bargains", "poundland", "card factory", "whsmith",
    "specsavers", "vision express", "halfords", "screwfix", "toolstation", "wickes", "b&q",
    "lloyds pharmacy", "well pharmacy", "shell", "esso", "texaco", "frankie & benny",
    "harvester", "beefeater", "brewers fayre", "toby carvery", "hungry horse", "papa john",
    "caffe nero", "caffè nero", "pret a manger", "wimpy", "five guys", "nando", "pizza express",
    "sports direct", "argos", "currys", "timpson", "barclays", "hsbc", "lloyds bank", "natwest",
    "nationwide", "santander", "tsb", "post office", "ladbrokes", "coral", "william hill",
    "betfred", "paddy power", "vodafone", "max spielmann", "cooplands", "bargain booze",
    "farmfoods", "heron foods", "jollyes", "pets at home", "dunelm", "hotel chocolat",
    "thorntons", "topps tiles", "booths", "euro garages", "jet ", "bp ", "morrisons daily",
    "papa johns", "taco bell", "tim hortons", "holiday inn", "best western", "hilton",
    "marriott", "ibis", "whitbread", "mcdonalds", "the original factory shop", "savers",
    "the works", "peacocks", "new look", "edinburgh woollen mill", "mountain warehouse",
    "trespass", "regatta", "cotswold outdoor", "go outdoors", "millets", "blacks",
    "screwfix", "howdens", "travis perkins", "jewson", "selco", "kwik fit", "ats euromaster",
    "national tyres", "formula one autocentres", "arnold clark", "evans halshaw",
    "jd sports", "clarks", "shoe zone", "select ", "specsavers", "dental care", "mydentist",
    "bupa", "rowlands pharmacy", "cohens", "day lewis", "asda express", "subway",
    "domino's", "dominos", "cash converters", "cex", "game ", "ee ", "o2 ", "three store",
    "betfred", "william hill", "rspca", "oxfam", "british heart foundation", "cancer research",
    "barnardo", "sue ryder", "hospice", "salvation army", "age uk", "mind ",
]

GENERIC = re.compile(r"\b(the|ltd|limited|llp|plc|and|&|co|uk|cafe|café|restaurant|"
                     r"hotel|pub|inn|bar)\b")


def norm_name(name: str) -> str:
    s = name.lower().replace("’", "'")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9& ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def core_name(name: str) -> str:
    return re.sub(r"\s+", " ", GENERIC.sub(" ", norm_name(name))).strip()


def is_chain(rec: dict) -> bool:
    if rec.get("brand"):
        return True
    n = " " + norm_name(rec["name"]) + " "
    return any(f" {norm_name(c)} " in n for c in CHAINS)


def similar(a: str, b: str) -> float:
    ca, cb = core_name(a), core_name(b)
    if not ca or not cb:
        ca, cb = norm_name(a), norm_name(b)
    if ca and cb and (ca in cb or cb in ca) and min(len(ca), len(cb)) >= 4:
        return 0.95
    return SequenceMatcher(None, ca, cb).ratio()


def record_id(rec: dict) -> str:
    key = f"{norm_name(rec['name'])}|{rec.get('postcode','').replace(' ','').upper()}|" \
          f"{round(rec['lat'],3)}|{round(rec['lon'],3)}"
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def _absorb(base: dict, other: dict) -> None:
    for k in ("website", "email", "phone", "postcode", "address", "town"):
        if not base.get(k) and other.get(k):
            base[k] = other[k]
    for k, v in (other.get("socials") or {}).items():
        base.setdefault("socials", {}).setdefault(k, v)
    base["sources"] = sorted(set(base["sources"]) | set(other["sources"]))
    for k in ("fsa_id", "fsa_rating", "fsa_rating_date", "authority", "osm_id"):
        if other.get(k) and not base.get(k):
            base[k] = other[k]
    base.setdefault("osm_tags", {}).update(other.get("osm_tags") or {})
    if other.get("brand"):
        base["brand"] = other["brand"]
    # Prefer the more specific OSM category when sectors agree
    if "OSM" in other["sources"] and other.get("category") and base["sector"] == other["sector"]:
        base["category"] = other["category"]


def combine(fsa: list[dict], osm: list[dict], log=print) -> tuple[list[dict], int]:
    """OSM records are matched onto FSA records (same business = similar name, close by)."""
    # 1. Collapse duplicate registrations inside FSA (same name + postcode).
    by_key: dict[str, dict] = {}
    for r in fsa:
        k = norm_name(r["name"]) + "|" + r["postcode"].replace(" ", "").upper()
        if k in by_key:
            _absorb(by_key[k], r)
        else:
            by_key[k] = r
    merged = list(by_key.values())

    # 2. Spatial bucket for fast neighbour lookups (~1 km cells)
    grid: dict[tuple[int, int], list[dict]] = {}
    for r in merged:
        grid.setdefault((int(r["lat"] * 100), int(r["lon"] * 60)), []).append(r)

    matched = 0
    for o in osm:
        gi, gj = int(o["lat"] * 100), int(o["lon"] * 60)
        best, best_s = None, 0.0
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for r in grid.get((gi + di, gj + dj), []):
                    d = haversine_km(o["lat"], o["lon"], r["lat"], r["lon"])
                    if d > 0.4:
                        continue
                    s = similar(o["name"], r["name"])
                    if (s >= 0.8 or (s >= 0.6 and d < 0.08)) and s > best_s:
                        best, best_s = r, s
        if best:
            _absorb(best, o)
            matched += 1
        else:
            merged.append(o)
            grid.setdefault((gi, gj), []).append(o)
    log(f"  matched {matched} OpenStreetMap places to hygiene-register entries")

    before = len(merged)
    kept = [r for r in merged if not is_chain(r)]
    for r in kept:
        r["id"] = record_id(r)
    return kept, before - len(kept)
