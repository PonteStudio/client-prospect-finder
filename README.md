# Client Prospect Finder

Ponte Studio's internal tool for finding local businesses whose online presence we could improve.

It looks at every business in a chosen area (default: 48 km around Workington, reaching Carlisle), works out whether each one has a website, only social media, or a website with fixable problems, and ranks them from highest to lowest priority. The output is a spreadsheet for Google Sheets that includes:

- **Online presence:** no website found, social media only, listing pages only, website not working, placeholder website, or has website
- **What caught our attention:** the findings, each with why it matters for us
- **Services to pitch**
- **Every contact route found**, plus a suggested best route
- **Sector** and a **★ core market** (hospitality) column for filtering
- **Status** and **Notes** columns for the team, kept between runs

## How to use it (in Claude Code on the web)

Open a chat on this repository and ask, for example:

> Run a prospect scan with the default area and put it in Google Sheets.
> Do a quick scan: 10 km around Keswick, hospitality only.
> Hand-check the top 20 hospitality leads that have no website found.

Claude follows `.claude/skills/find-prospects/SKILL.md`.

## Commands

```bash
python -m prospect_finder --help
python -m prospect_finder --centre Keswick --radius-km 10 --sectors Hospitality
```

## Data sources (all free)

- **Food Standards Agency hygiene-rating register:** food and hospitality businesses
- **OpenStreetMap (Overpass API):** all sectors, sometimes with website, phone, email and social links
- **The businesses' own websites:** objective checks
- **Internet Archive:** when each site was first seen and last changed

See `docs/DECISIONS.md` for every decision made so far and the list of planned improvements.
