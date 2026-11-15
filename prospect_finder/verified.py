"""Manual / search-verified facts, kept in data/verified.csv (committed to the repo).

When Claude (or you) checks a business by hand — e.g. searches the web for its website
or social pages — the result goes in this file. Every later run applies it, so the
work is never lost between chats.
"""
from __future__ import annotations

import csv
import os

FIELDS = ["ID", "Name", "Checked on", "Website", "Facebook", "Instagram", "Other links",
          "No website confirmed", "Notes", "Exclude (reason)"]


def load(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["ID"]: r for r in csv.DictReader(f) if r.get("ID")}


def apply(records: list[dict], path: str) -> int:
    facts = load(path)
    n = 0
    for r in records:
        v = facts.get(r["id"])
        if not v:
            continue
        n += 1
        if v.get("Website"):
            r["website"] = v["Website"].strip()
            r["website_found_by"] = f"checked by hand {v.get('Checked on','')}".strip()
        socials = r.setdefault("socials", {})
        if v.get("Facebook"):
            socials["facebook"] = v["Facebook"].strip()
        if v.get("Instagram"):
            socials["instagram"] = v["Instagram"].strip()
        if v.get("Other links"):
            r.setdefault("listings", []).extend(x.strip() for x in v["Other links"].split(";") if x.strip())
        r["verified"] = {"date": v.get("Checked on", ""),
                         "no_website": (v.get("No website confirmed") or "").strip().lower() in ("yes", "y", "true", "1"),
                         "notes": v.get("Notes", ""),
                         "exclude": (v.get("Exclude (reason)") or "").strip()}
    return n
