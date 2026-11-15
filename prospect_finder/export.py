"""Write the ranked list as CSV (uploaded to Google Sheets) plus a full JSON dump."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os

COLUMNS = [
    "Rank", "Score", "Name", "Sector", "Category", "Core market", "Town", "Postcode",
    "Distance (km)", "Council area", "Online presence", "What caught our attention",
    "Services to pitch", "Confidence", "Website", "Website found by", "Email", "Phone",
    "Facebook", "Instagram", "Other links", "Best contact route",
    "Website last changed (archive)", "Copyright year", "Platform",
    "Score breakdown", "Sources", "Hygiene rating", "Address",
    "Status", "Notes", "First seen", "Last checked", "ID",
]
KEEP_FROM_PREVIOUS = ("Status", "Notes", "First seen")


def load_previous(path: str | None) -> dict[str, dict]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {row["ID"]: row for row in csv.DictReader(f) if row.get("ID")}


def to_row(rank: int, r: dict, today: str, prev: dict) -> dict:
    a = r.get("audit") or {}
    socials = r.get("all_socials") or {}
    other = [v for k, v in socials.items() if k not in ("facebook", "instagram")]
    other += r.get("listings") or []
    p = r["score_parts"]
    row = {
        "Rank": rank,
        "Score": r["score"],
        "Name": r["name"],
        "Sector": r["sector"],
        "Category": r.get("category", ""),
        "Core market": "★ Yes" if r["core_market"] else "",
        "Town": r.get("town", ""),
        "Postcode": r.get("postcode", ""),
        "Distance (km)": r["distance_km"],
        "Council area": r.get("authority", ""),
        "Online presence": r["presence"],
        "What caught our attention": "\n".join("• " + f for f in r["findings"]),
        "Services to pitch": ", ".join(r["services"]),
        "Confidence": r["confidence"],
        "Website": r.get("website", ""),
        "Website found by": r.get("website_found_by", "listed on OpenStreetMap" if r.get("website") else ""),
        "Email": ", ".join(r.get("all_emails") or []),
        "Phone": ", ".join(r.get("all_phones") or []),
        "Facebook": socials.get("facebook", ""),
        "Instagram": socials.get("instagram", ""),
        "Other links": "\n".join(other[:4]),
        "Best contact route": r["best_contact"],
        "Website last changed (archive)": a.get("archive_last_change", ""),
        "Copyright year": a.get("copyright_year") or "",
        "Platform": a.get("platform", ""),
        "Score breakdown": f"need {p['opportunity']} · distance {p['distance']} · "
                           f"size {p['strength']} · contact {p['contactability']}",
        "Sources": " + ".join("Food hygiene register" if s == "FSA" else "OpenStreetMap"
                              for s in r["sources"]),
        "Hygiene rating": r.get("fsa_rating", "") or "",
        "Address": r.get("address", ""),
        "Status": "New",
        "Notes": "",
        "First seen": today,
        "Last checked": today,
        "ID": r["id"],
    }
    if r["id"] in prev:
        for k in KEEP_FROM_PREVIOUS:
            if prev[r["id"]].get(k):
                row[k] = prev[r["id"]][k]
    return row


def write(records: list[dict], out_dir: str, previous: str | None, run_info: dict) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    today = dt.date.today().isoformat()
    prev = load_previous(previous)
    records = sorted(records, key=lambda r: (-r["score"], r["distance_km"]))
    rows = [to_row(i, r, today, prev) for i, r in enumerate(records, 1)]
    csv_path = os.path.join(out_dir, "prospects.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    json_path = os.path.join(out_dir, "prospects_full.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"run": run_info, "records": records}, f, ensure_ascii=False, indent=1, default=str)
    return {"csv": csv_path, "json": json_path, "rows": len(rows)}
