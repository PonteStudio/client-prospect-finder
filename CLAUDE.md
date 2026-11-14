# Client Prospect Finder — notes for Claude

Internal tool for **Ponte Studio** (web design, branding, landing pages, SEO, social media,
Google Business Profiles, consulting). It finds local businesses whose online presence could be
improved and ranks them, so the team can contact the best leads first.

The owner uses **Claude Code in the browser only**. Never ask them to install anything locally.
Explain things in plain language — they are not a developer.

## Git workflow (agreed — always follow)

- `main` is the only long-lived branch.
- Each new chat works on **one temporary branch** (the session's designated branch).
- When the work of a chat is done: push the branch, open a pull request into `main`,
  merge it (squash), and the branch is deleted automatically on merge
  (repo setting "Automatically delete head branches"). If that setting is off, delete the branch
  after merging.
- Never leave work only on a temporary branch, never commit straight to `main`.

## How to run a scan

```bash
python -m prospect_finder                                   # default: 48 km around Workington
python -m prospect_finder --centre Keswick --radius-km 10   # quick, smaller check
python -m prospect_finder --sectors Hospitality             # one sector only
python -m prospect_finder --help                            # all options
```

Results go to `output/prospects.csv` (plus `prospects_full.json`, `run_summary.json`).
A full default run takes roughly 20–40 minutes, mostly the OpenStreetMap download (cached in
`cache/` for 72 h) and the website checks. `--no-archive` and `--no-discovery` make it faster.

The skill in `.claude/skills/find-prospects/` describes the full routine, including uploading
the results to Google Sheets and hand-checking the top leads.

## Rules of the road

- Free sources only for now (see `docs/DECISIONS.md`). Do not add paid APIs without asking.
- Be polite to public servers: identify the tool in the User-Agent, keep concurrency modest,
  don't scrape search engines or social networks.
- Hand-checked facts live in `data/verified.csv` — commit changes to it, it is the memory
  between chats.
- Record every new decision in `docs/DECISIONS.md` and ideas in its "Ways to improve" section.
- Do not draft outreach messages yet — the owner asked for data gathering only for now.
