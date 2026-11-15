"""Command line entry point.

Examples
  python -m prospect_finder                                  # defaults: 48 km around Workington
  python -m prospect_finder --centre Keswick --radius-km 10  # quick local check
  python -m prospect_finder --sectors Hospitality --radius-km 25
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import sys
import time

from . import config, export, merge, score, verified, websites
from .geo import resolve_centre
from .sources import fsa, osm


def log(msg: str) -> None:
    print(msg, flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="prospect_finder", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--centre", default=config.DEFAULT_CENTRE_NAME,
                    help="Town name, or 'lat,lon' (default: Workington)")
    ap.add_argument("--radius-km", type=float, default=config.DEFAULT_RADIUS_KM)
    ap.add_argument("--sectors", default="all",
                    help="Comma-separated sectors to keep, or 'all'. Options: "
                         + ", ".join(config.DEFAULT_SECTORS))
    ap.add_argument("--england-only", action="store_true",
                    help="Drop businesses registered with Scottish councils")
    ap.add_argument("--no-discovery", action="store_true",
                    help="Skip guessing websites for businesses with none listed (faster)")
    ap.add_argument("--no-archive", action="store_true", help="Skip Internet Archive history (faster)")
    ap.add_argument("--limit", type=int, default=0, help="Only process N businesses (testing)")
    ap.add_argument("--previous", help="CSV export of the Google Sheet, to keep Status/Notes")
    ap.add_argument("--verified", default="data/verified.csv",
                    help="Hand-checked facts to apply (website/social links found by search)")
    ap.add_argument("--out", default="output")
    ap.add_argument("--cache", default="cache")
    args = ap.parse_args(argv)

    t0 = time.time()
    lat, lon, label = resolve_centre(args.centre)
    sectors = None if args.sectors.strip().lower() == "all" else \
        {s.strip().lower() for s in args.sectors.split(",")}
    log(f"Search: {args.radius_km:g} km around {label} ({lat:.4f}, {lon:.4f}); "
        f"sectors: {args.sectors}")

    log("1/5 Food hygiene register…")
    f_recs = fsa.fetch(lat, lon, args.radius_km, log=log)
    log(f"  {len(f_recs)} food businesses")
    log("2/5 OpenStreetMap…")
    o_recs = osm.fetch(lat, lon, args.radius_km, log=log, cache_dir=args.cache)
    log(f"  {len(o_recs)} named places")

    log("3/5 Combining and removing chains…")
    recs, chains = merge.combine(f_recs, o_recs, log=log)
    if sectors:
        recs = [r for r in recs if r["sector"].lower() in sectors]
    if args.england_only:
        scot = {"Dumfries and Galloway", "South Lanarkshire", "Scottish Borders"}
        recs = [r for r in recs if r.get("authority") not in scot and
                not (r.get("postcode", "").upper().startswith("DG"))]
    if args.limit:
        recs.sort(key=lambda r: (r["lat"] - lat) ** 2 + (r["lon"] - lon) ** 2)
        recs = recs[: args.limit]
    log(f"  {len(recs)} businesses kept ({chains} chain outlets removed)")

    n = verified.apply(recs, args.verified)
    if n:
        log(f"  applied {n} hand-checked records from {args.verified}")

    log("4/5 Finding and checking websites…")
    websites.run_all(recs, log=log, archive=not args.no_archive,
                     discover_sectors=set() if args.no_discovery else None)

    log("5/5 Scoring…")
    for r in recs:
        score.evaluate(r, (lat, lon), args.radius_km)
    info = {"centre": label, "lat": lat, "lon": lon, "radius_km": args.radius_km,
            "sectors": args.sectors, "date": dt.datetime.now().isoformat(timespec="minutes"),
            "businesses": len(recs), "chains_removed": chains}
    res = export.write(recs, args.out, args.previous, info)

    pres = collections.Counter(r["presence"] for r in recs)
    summary = {**info, "presence": dict(pres.most_common()),
               "sectors_found": dict(collections.Counter(r["sector"] for r in recs).most_common()),
               "minutes": round((time.time() - t0) / 60, 1)}
    with open(os.path.join(args.out, "run_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    log("\nDone in %.1f min. %d businesses → %s" % (summary["minutes"], res["rows"], res["csv"]))
    for k, v in pres.most_common():
        log(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
