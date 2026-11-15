---
name: find-prospects
description: Run the Ponte Studio prospect scan for an area, upload the ranked list to Google Sheets, and optionally hand-check the top leads. Use when the user asks to find prospects/leads/clients, run a scan, or refresh the prospect sheet.
---

# Find prospects

## 1. Agree the search (ask only what's missing)

- **Centre**: a town name (Workington, Keswick, Carlisle…) or `lat,lon`. Default Workington.
- **Radius** in km. Default 48 (reaches Carlisle). Small checks: 5–15 km.
- **Sectors**: `all` (default) or a list, e.g. `Hospitality`.
- England only? (the default circle crosses the Solway into Dumfries & Galloway).

## 2. Keep the team's work

If the Google Sheet already exists, read its `ID`, `Status`, `Notes`, `First seen` columns with
the Google Sheets connector and save them as `cache/previous.csv`, then pass
`--previous cache/previous.csv` so nothing the team typed is lost.

## 3. Run

```bash
python -m prospect_finder --centre <town> --radius-km <km> [--sectors ...] [--previous cache/previous.csv]
```

Run it in the background for big areas and give the user short progress updates.

## 4. Upload to Google Sheets

Upload `output/prospects.csv` with the Google Drive connector `create_file`
(contentMimeType `text/csv`, it converts to a Sheet), using a file reference for the content.
Name it `Ponte prospects – <centre> <radius> km – <date>`. Then format it: freeze row 1 and
columns A–C, turn on a filter, wrap the "What caught our attention" column, set sensible column
widths. Give the user the link.

## 5. Optional: hand-check top leads

Rows with Confidence "Low"/"Medium" and Online presence "No website found" may simply be
missing from open data. For the top N the user picks (e.g. 20 hospitality leads), use web search
to look for each business's website, Facebook and Instagram. Record each result in
`data/verified.csv` (one row per business, use the `ID` column from the CSV), then re-run with
the cached data and re-upload. Commit `data/verified.csv`.

## 6. Best Leads (top 50)

When asked for the best leads: shortlist from `output/prospects_full.json` (drop public
services, clubs, franchises, non-trading), hand-check the strongest with web search, record
every check in `data/verified.csv` (use "Exclude (reason)" for closed/chain/for-sale), rescore
with `python -m prospect_finder.rescore`, then write a ranked CSV (Priority, why, what to pitch,
contacts, Checked = hand-checked / from scan data) and upload it as its own Sheet.

## 7. Finish

Summarise: how many businesses, the split by online presence, the top 10, anything odd.
Note new decisions/ideas in `docs/DECISIONS.md`. Commit, open a PR to `main`, merge.
