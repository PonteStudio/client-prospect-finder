# Decisions log & ways to improve

Living document. Add a dated line whenever something is decided or changed.

## Decisions

### Goal and scope
| Date | Decision |
|---|---|
| 2026-11-10 | Build an internal tool that finds local businesses with no website, social-only presence, or a website that can be objectively improved (SEO, design, accessibility, speed), and ranks them by priority. |
| 2026-11-10 | Ponte Studio services to match against: websites, branding, landing pages, consulting, social media, Google Business Profiles, SEO. |
| 2026-11-10 | Core market to start: **small hospitality businesses** (cafés, pubs, restaurants, hotels, B&Bs, campsites…). Other sectors are kept and tagged so the team can branch out — handled with a **Sector** column + **Core market ★** column to filter on, not by changing the score. |
| 2026-11-14 | **Prototype = data gathering only.** No outreach message drafts for now. Each lead instead gets notes on *what caught our attention* and *why it matters for us*. |

### Area
| Date | Decision |
|---|---|
| 2026-11-10 | Region: Cumbria, UK. |
| 2026-11-14 | Default search: circle centred on **Workington** with a **48 km** radius (reaches Carlisle, ~47 km). Centre and radius are settings on every run (`--centre`, `--radius-km`) so small or large checks are possible. |
| 2026-11-14 | The default circle crosses the Solway Firth into Dumfries & Galloway (Scotland). Those businesses are **kept** and tagged in "Council area"; `--england-only` drops them. |

### Data sources (free only)
| Date | Decision |
|---|---|
| 2026-11-10 | Start **free-only**. Paid sources (e.g. Google Places API) only if the prototype proves useful. |
| 2026-11-14 | Prototype uses only what is reachable from the Claude Code browser session without adding anything: **Food Standards Agency hygiene register** (near-complete list of food/hospitality businesses), **OpenStreetMap via Overpass** (all sectors, sometimes website/phone/email/social links), **the businesses' own websites**, and the **Internet Archive** (site history). |
| 2026-11-14 | National chains and charity shops are removed automatically (OSM `brand` tag + a name list in `merge.py`). |
| 2026-11-14 | Websites not listed anywhere are searched for for free by (a) trying the domain of a business email address and (b) guessing domains from the business name — a guess is accepted **only if the page shows the business's postcode or phone number**. |
| 2026-11-14 | Search engines and social networks are **not scraped** (terms of service + the session blocks it). Instead, top leads can be **hand-checked by Claude with web search**, and the results are stored in `data/verified.csv` so they are reused on every later run. |
| 2026-11-14 | Sites that block automated visitors (bot protection, HTTP 403/429) are **respected, not bypassed**: they are labelled "Website (could not check)" for a person to look at. |
| 2026-11-14 | The browser session can only open secure (https) sites. If a site won't load securely, a public DNS lookup (dns.google) decides: domain gone → "Website not working"; domain alive → "Website – no secure version" (http-only or down). |
| 2026-11-14 | OpenStreetMap is downloaded in ~12 km tiles with back-off because the public Overpass servers are busy (a full area took ~2.5 h the first time). The Geofabrik bulk download is not reachable from the session. |
| 2026-11-14 | Google PageSpeed/Lighthouse API needs a key (returns "quota exceeded" without one), so the prototype does its own objective checks instead. |

### Scoring (0–100, weights in `config.py`)
| Part | Points | Basis |
|---|---|---|
| Need / opportunity | 55 | Website not working ≈ highest, then social-only, listing-pages-only, placeholder site, confirmed no website, unverified no website; for sites: sum of weighted issues (no HTTPS, not mobile-friendly, stale content, old tech, missing SEO basics, accessibility gaps, PDF menus, no online booking, …) |
| Distance | 20 | Linear from the centre to the edge of the chosen radius |
| Size / value | 15 | Rough, open-data only: business type (hotel > restaurant/pub > café > takeaway…), star/room tags, how long the site has existed |
| Contactability | 10 | Email, phone, social accounts found |

"Unverified no website" is scored lower than "confirmed" because absence from open data does not prove absence online. The **Confidence** column says how sure the tool is.

### Output
| Date | Decision |
|---|---|
| 2026-11-10 | Results live in a **Google Sheet** (filter by sector/core market there). |
| 2026-11-10 | List **every contact route found** (email, phone, Facebook, Instagram, other links) and a **best contact route** suggestion. Social media counts as a valid route, especially for social-only businesses. |
| 2026-11-14 | Columns `Status`, `Notes`, `First seen` belong to the team; re-runs carry them over (`--previous`). |

### Best Leads list
| Date | Decision |
|---|---|
| 2026-11-15 | Two Google Sheets: the **full list** ("Ponte prospects – Workington 48 km – 2026-11-14") and a separate **Best Leads** sheet ("Ponte – Best Leads (top 50) – 2026-11-15") with the top 50 to contact first, in priority order. |
| 2026-11-15 | Best Leads are picked by Claude after analysis, not just by score: filter out public services, clubs, franchises and non-trading places → shortlist ~110 → hand-check the strongest by web search (still trading? new website? size/popularity) → order by gap × size × confidence, hospitality first. |
| 2026-11-15 | Hand-check results live in `data/verified.csv`, including an "Exclude (reason)" column (closed, chain, for sale…). Excluded rows stay in the full list with score 0. |
| 2026-11-15 | Lesson: many "website not working" leads from OpenStreetMap are just **old links** – the business moved to a new domain. Always verify before contacting. |

### Way of working
| Date | Decision |
|---|---|
| 2026-11-10 | Run manually through **Claude Code in the browser** (no local installs). Automating with a scheduled agent is a later option. |
| 2026-11-14 | GitHub repo `client-prospect-finder`. One temporary branch per chat → pull request → merge into `main` → branch deleted automatically. Only `main` lives on. |
| 2026-11-14 | First full scan uploaded: Google Sheet "Ponte prospects – Workington 48 km – 2026-11-14" (tabs: Prospects, About this run). |
| 2026-11-14 | `python -m prospect_finder.rescore` re-scores a saved run (e.g. after hand-checks) without downloading everything again. |
| 2026-11-14 | Code: small Python package (`prospect_finder/`), plus a Node/Playwright helper that re-checks JavaScript-built sites in a real browser. |

## Ways to improve

Roughly in order of value.

1. **Google Places API (paid, generous free tier).** Biggest single upgrade: reliable website links, Google Business Profile completeness (photos, hours, reviews, owner replies — we sell GBP work but can't measure it yet), rating and review count as a size signal, and coverage of non-food businesses.
2. **Verify "no website" leads at scale.** Today it's a manual web search per lead. Options: a search API with a free tier (e.g. Brave Search API), or Places API above.
3. **Social media activity.** Record follower counts and last-post date for social-only businesses (manual or via an approved API), so "active on Instagram, no website" leads rise to the top.
4. **Lighthouse scores** (performance, accessibility, SEO, best practice) via a free PageSpeed API key, or by running Lighthouse locally in the session's Chromium for the top ~100 sites.
5. **Design score.** Take desktop + mobile screenshots of each site and have Claude rate them against a fixed checklist (dated look, hierarchy, mobile layout, call-to-action clarity). Keep it weighted lower than objective checks.
6. **Company size & legal type** from Companies House (free API key): limited company vs sole trader matters for UK email-marketing rules (PECR) and is a size signal.
7. **More sources for non-food sectors**: VisitCumbria / Lake District accommodation listings, local business directories, Cumbria Chamber of Commerce members.
8. **Better duplicate matching** between sources (fuzzy address matching, phone matching).
9. **Change tracking between runs**: highlight new businesses, sites that changed, leads that improved.
10. **Outreach drafts** (deliberately postponed): one tailored opening message per lead and channel, in Ponte Studio's voice.
11. **Automation**: scheduled re-runs with a cloud agent once the process is proven; push only new leads to the Sheet.
12. **Simple web UI** (map + radius slider) if running from chat becomes limiting.
13. **Respect contact rules**: flag sole traders (consent needed for marketing email under PECR) and check the TPS before calls.

## Known limitations (prototype)

- About half of the Best Leads are hand-checked; the rest are marked "From scan data" in the sheet.

- Plain http:// pages can't be opened from the browser session, so http-only sites are flagged from DNS evidence rather than inspected.
- Instagram links are rarely in open data, so "Social media only" is undercounted (most social-only businesses currently appear as "No website found").

- Only food/hospitality businesses are near-complete (hygiene register). Other sectors depend on OpenStreetMap coverage, which is patchy outside towns.
- "No website found" is often "we couldn't find it" — check before contacting (see Confidence).
- The public OpenStreetMap server is slow and sometimes refuses requests; a full-area download can take a while and some tiles may be skipped (re-run to fill them; finished tiles are cached for 72 h within one session).
- No Google Business Profile data, no review counts, no social activity yet.
