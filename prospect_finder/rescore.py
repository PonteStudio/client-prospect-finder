"""Re-score a saved run without downloading everything again.

  python -m prospect_finder.rescore                       # re-apply data/verified.csv + scoring
  python -m prospect_finder.rescore --recheck-errors      # also re-test sites that failed

Uses output/prospects_full.json from the last full run (same chat session).
"""
from __future__ import annotations

import argparse
import collections
import json
from concurrent.futures import ThreadPoolExecutor

from . import config, export, score, verified, websites


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="prospect_finder.rescore")
    ap.add_argument("--from", dest="src", default="output/prospects_full.json")
    ap.add_argument("--recheck-errors", action="store_true")
    ap.add_argument("--verified", default="data/verified.csv")
    ap.add_argument("--previous")
    ap.add_argument("--out", default="output")
    args = ap.parse_args(argv)

    data = json.load(open(args.src, encoding="utf-8"))
    info, recs = data["run"], data["records"]
    n = verified.apply(recs, args.verified)
    print(f"{len(recs)} businesses loaded; {n} hand-checked records applied")

    # Sites newly added by hand-checks, or failed ones on request, get (re-)audited.
    def needs_check(r):
        a = r.get("audit")
        if not a:
            return True
        return args.recheck_errors and (a.get("status") in ("error", "blocked", "no_https")
                                        or a.get("placeholder"))

    todo = [r for r in recs if r.get("website") and needs_check(r)]
    if todo:
        print(f"checking {len(todo)} websites…")

        def one(r):
            r["audit"] = websites.audit(r)
            r["audit"].update(websites.archive_history(r["website"]))
        with ThreadPoolExecutor(config.AUDIT_WORKERS) as ex:
            list(ex.map(one, todo))
        websites.rerender_thin(todo, print)

    for r in recs:
        score.evaluate(r, (info["lat"], info["lon"]), info["radius_km"])
    res = export.write(recs, args.out, args.previous, info)
    print(f"{res['rows']} rows → {res['csv']}")
    for k, v in collections.Counter(r["presence"] for r in recs).most_common():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
