"""Find and audit business websites using only free, public methods.

1. Classify the link we already have (real website, social page, directory listing).
2. For businesses with no link, try to *find* their website:
   - the domain of a business email address (info@smithsbakery.co.uk -> smithsbakery.co.uk)
   - likely domains built from the business name (the-old-bakery -> theoldbakery.co.uk),
     accepted only if the page mentions the business's postcode or phone number.
3. Audit each website: objective checks on the homepage + the Internet Archive history.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import config

SOCIAL_DOMAINS = {
    "facebook.com": "facebook", "fb.com": "facebook", "fb.me": "facebook",
    "instagram.com": "instagram", "tiktok.com": "tiktok", "twitter.com": "twitter",
    "x.com": "twitter", "linktr.ee": "linktree", "linkedin.com": "linkedin",
    "youtube.com": "youtube",
}
LISTING_DOMAINS = (
    "tripadvisor.", "booking.com", "airbnb.", "yell.com", "thebestof.co.uk", "visitcumbria.com",
    "visitlakedistrict.com", "lakedistrict.gov.uk", "google.com", "goo.gl", "g.page",
    "just-eat.co.uk", "justeat.", "deliveroo.", "ubereats.", "hungryhouse", "opentable.",
    "cylex-uk.co.uk", "scoot.co.uk", "freeindex.co.uk", "checkatrade.com", "hotels.com",
    "expedia.", "sykescottages.co.uk", "cottages.com", "hoseasons.co.uk", "pubsgalore.co.uk",
    "beerintheevening.com", "whatpub.com", "find-and-update.company-information.service.gov.uk",
    "nhs.uk", "visitscotland.com", "cumbria.gov.uk", "cumberland.gov.uk",
)
FREE_BUILDER = ("wixsite.com", "weebly.com", "wordpress.com", "blogspot.", "square.site",
                "godaddysites.com", "webador.", "jimdosite.com", "site123.me", "business.site",
                "carrd.co", "strikingly.com", "mozello.", "ueniweb.com", "yolasite.com")
FREEMAIL = ("gmail.", "googlemail.", "hotmail.", "outlook.", "live.", "yahoo.", "btinternet.",
            "aol.", "icloud.", "me.com", "sky.com", "talktalk.", "virginmedia.", "msn.",
            "btopenworld.", "tiscali.", "ntlworld.", "mail.com", "protonmail.", "zoho.")

UA = {"User-Agent": config.USER_AGENT, "Accept-Language": "en-GB,en;q=0.8"}
THIS_YEAR = dt.date.today().year


# ---------------------------------------------------------------- link types

def domain_of(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    d = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return d[4:] if d.startswith("www.") else d


def link_kind(url: str) -> tuple[str, str]:
    """Returns (kind, label) where kind is 'website' | 'social' | 'listing'."""
    d = domain_of(url)
    for sd, net in SOCIAL_DOMAINS.items():
        if d == sd or d.endswith("." + sd):
            return "social", net
    if any(x in d for x in LISTING_DOMAINS):
        return "listing", d
    return "website", d


def classify_links(rec: dict) -> None:
    """Move social/listing URLs out of the website field."""
    url = (rec.get("website") or "").strip()
    if not url:
        return
    kind, label = link_kind(url)
    if kind == "social":
        rec.setdefault("socials", {}).setdefault(label, url)
        rec["website"] = ""
    elif kind == "listing":
        rec.setdefault("listings", []).append(url)
        rec["website"] = ""


# ---------------------------------------------------------------- discovery

def _slug_variants(name: str, town: str) -> list[str]:
    n = name.lower().replace("&", " and ").replace("’", "").replace("'", "")
    n = re.sub(r"\(.*?\)", " ", n)
    n = re.sub(r"\b(ltd|limited|llp|plc|t/a.*)$", " ", n)
    words = re.findall(r"[a-z0-9]+", n)
    if not words or len("".join(words)) < 4:
        return []
    bases = {"".join(words), "-".join(words)}
    if words[0] == "the" and len(words) > 1:
        bases |= {"".join(words[1:]), "-".join(words[1:])}
    t = re.sub(r"[^a-z]", "", (town or "").lower())
    if t and len(words) <= 3:
        bases.add("".join(words) + t)
    out = []
    for b in sorted(bases, key=len):
        if 4 <= len(b) <= 40:
            out += [f"{b}.co.uk", f"{b}.com", f"{b}.uk"]
    return out[:9]


class _Slow(Exception):
    pass


def _get(url: str, timeout=None, max_bytes=3_000_000):
    """GET with a hard overall deadline and size cap (some servers trickle data forever)."""
    limit = timeout or config.HTTP_TIMEOUT
    start = time.time()
    with requests.get(url, headers=UA, timeout=min(limit, 8), allow_redirects=True,
                      stream=True) as r:
        chunks, size = [], 0
        for chunk in r.iter_content(65536):
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                break
            if time.time() - start > limit + 5:
                raise _Slow(url)
        r._content = b"".join(chunks)
        r._content_consumed = True
        return r


def _page_mentions(html: str, rec: dict) -> str:
    text = re.sub(r"\s+", "", html.lower())
    pc = (rec.get("postcode") or "").replace(" ", "").lower()
    if pc and len(pc) >= 5 and pc in text:
        return "postcode"
    ph = re.sub(r"\D", "", rec.get("phone") or "")
    if len(ph) >= 9 and ph[-9:] in re.sub(r"\D", "", html):
        return "phone"
    return ""


def discover(rec: dict) -> None:
    """Try to find a website for a record that has none. Sets website + website_found_by."""
    if rec.get("website"):
        return
    # a) domain of a business email
    em = rec.get("email") or ""
    if "@" in em:
        d = em.split("@", 1)[1].strip().lower()
        if not any(d.startswith(f) or f in d for f in FREEMAIL):
            for url in (f"https://{d}", f"https://www.{d}", f"http://{d}"):
                try:
                    r = _get(url, timeout=10)
                    if r.status_code < 400 and len(r.text) > 500:
                        rec["website"] = r.url
                        rec["website_found_by"] = "domain of their email address"
                        return
                except Exception:  # noqa: BLE001
                    continue
    # b) guess domains from the name, accept only if the page mentions their postcode/phone
    for dom in _slug_variants(rec["name"], rec.get("town", "")):
        try:
            r = _get(f"https://{dom}", timeout=8)
        except Exception:  # noqa: BLE001
            continue
        if r.status_code >= 400 or len(r.text) < 500:
            continue
        hit = _page_mentions(r.text, rec)
        if hit:
            rec["website"] = r.url
            rec["website_found_by"] = f"guessed domain {dom}, confirmed by {hit} on the page"
            return


# ---------------------------------------------------------------- audit

YEAR_RE = re.compile(r"(?:©|&copy;|copyright)\s*(?:\D{0,20})((?:19|20)\d{2})(?:\s*[-–]\s*((?:19|20)\d{2}))?",
                     re.I)
JQ_RE = re.compile(r"jquery[.-]?(\d+)\.(\d+)(?:\.(\d+))?(?:\.min)?\.js", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BOOKING_HINTS = ("opentable", "resdiary", "tablein", "designmynight", "bookatable", "sevenrooms",
                 "freetobook", "eviivo", "little hotelier", "littlehotelier", "nightsbridge",
                 "beds24", "cloudbeds", "booking-button", "bookingbutton", "siteminder",
                 "thebookingbutton", "superbookings", "guestline", "fresha", "treatwell",
                 "booksy", "timely", "calendly", "book now", "book a table", "book online",
                 "check availability")


def audit(rec: dict) -> dict:
    url = rec["website"]
    if "://" not in url:
        url = "http://" + url
    res: dict = {"checked_url": url, "issues": []}
    r = None
    last_err = ""
    # Try the listed address, then the http/https and www variants, before calling it dead.
    d = domain_of(url)
    path = urlparse(url).path
    variants = []
    for v in (url.replace("http://", "https://", 1), f"https://{d}", f"https://www.{d}", url,
              f"http://{d}", f"http://www.{d}"):
        if v not in variants:
            variants.append(v)
    t0 = time.time()
    for v in variants:
        try:
            t0 = time.time()
            r = _get(v)
            break
        except requests.exceptions.SSLError:
            last_err = "security certificate error"
        except Exception as e:  # noqa: BLE001
            last_err = type(e).__name__
    if r is None:
        dns = dns_status(d)
        if dns == "missing":
            res.update(status="error", error="the domain no longer exists (expired or never set up)")
        elif dns == "ok":
            # Domain is live but nothing answered securely. Either the site only works on old,
            # insecure http:// (which this checker can't open) or the hosting is down.
            res.update(status="no_https", error="the site doesn't load over a secure (https) "
                                                "connection – it is either http-only or down")
        else:
            res.update(status="error", error=f"the site does not load at all ({last_err})")
        return res
    # A listed deep link that 404s doesn't mean the site is broken: try the homepage.
    if r.status_code in (404, 410) and urlparse(r.url).path not in ("", "/"):
        try:
            root = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}/"
            t0 = time.time()
            r2 = _get(root)
            if r2.status_code < 400:
                r = r2
                res["note"] = "listed link was out of date; checked the homepage instead"
        except Exception:  # noqa: BLE001
            pass
    res["load_seconds"] = round(time.time() - t0, 1)
    res["final_url"] = r.url
    res["http_status"] = r.status_code
    if r.status_code in (401, 403, 429, 503, 999):
        # Usually bot protection (e.g. Cloudflare), not a broken site. We respect it and
        # leave the site for a person to look at.
        res.update(status="blocked", error=f"the site does not allow automated checks ({r.status_code})")
        return res
    if r.status_code >= 400:
        res.update(status="error", error=f"the site returns error {r.status_code}")
        return res
    res["html_kb"] = round(len(r.content) / 1024)
    res["status"] = "ok"
    res["https"] = r.url.startswith("https://")
    res.update(analyse(r.text or "", r.url, res["https"]))
    return res


def dns_status(domain: str) -> str:
    """'ok', 'missing' (NXDOMAIN) or 'unknown', via Google's public DNS-over-HTTPS."""
    try:
        r = requests.get("https://dns.google/resolve", params={"name": domain, "type": "A"},
                         headers=UA, timeout=10)
        st = r.json().get("Status")
        if st == 3:
            return "missing"
        if st == 0:
            return "ok" if r.json().get("Answer") else "missing"
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def analyse(html: str, final_url: str, https: bool) -> dict:
    """Objective checks on one page's HTML."""
    res: dict = {"placeholder": False}
    soup = BeautifulSoup(html, "lxml")
    low = html.lower()
    final_dom = domain_of(final_url)
    kind, label = link_kind(final_url)
    if kind != "website":
        res["redirects_to"] = label

    # parked / placeholder pages
    text = soup.get_text(" ", strip=True)
    res["words"] = len(text.split())
    if res["words"] < 80 and re.search(r"domain (is )?for sale|this domain (has been|is) (registered|parked)|"
                 r"coming soon|under construction|website is under maintenance|"
                 r"buy this domain|parked free", text[:3000], re.I):
        res["placeholder"] = True

    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    res["title"] = title[:120]
    md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    res["meta_description"] = bool(md and md.get("content", "").strip())
    vp = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    res["viewport"] = bool(vp)
    res["zoom_blocked"] = bool(vp and re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b",
                                                vp.get("content", ""), re.I))
    res["h1"] = len(soup.find_all("h1"))
    imgs = soup.find_all("img")
    res["images"] = len(imgs)
    res["images_no_alt"] = sum(1 for i in imgs if not (i.get("alt") or "").strip())
    html_tag = soup.find("html")
    res["lang"] = bool(html_tag and html_tag.get("lang"))
    res["schema_local_business"] = bool(re.search(
        r'"@type"\s*:\s*"(LocalBusiness|Restaurant|Hotel|LodgingBusiness|FoodEstablishment|'
        r'BarOrPub|CafeOrCoffeeShop|Store|[A-Za-z]*Business)"', html))
    res["open_graph"] = bool(soup.find("meta", attrs={"property": "og:title"}))

    gen = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    res["generator"] = (gen.get("content", "") if gen else "")[:60]
    for pat, name in ((r"wp-content|wp-includes", "WordPress"), (r"static\.wixstatic|wix\.com", "Wix"),
                      (r"squarespace", "Squarespace"), (r"shopify", "Shopify"),
                      (r"joomla", "Joomla"), (r"webflow", "Webflow"), (r"godaddy", "GoDaddy builder"),
                      (r"weebly", "Weebly"), (r"jimdo", "Jimdo"), (r"drupal", "Drupal")):
        if re.search(pat, low):
            res["platform"] = name
            break

    years = []
    for m in YEAR_RE.finditer(text[-4000:] + " " + text[:500]):
        years += [int(y) for y in m.groups() if y]
    years = [y for y in years if 1995 <= y <= THIS_YEAR]
    res["copyright_year"] = max(years) if years else None

    jq = [tuple(int(x or 0) for x in m.groups()) for m in JQ_RE.finditer(html)]
    res["jquery"] = ".".join(map(str, min(jq))) if jq else ""
    res["old_markup"] = sorted({t for t in ("font", "center", "marquee", "frameset", "frame", "blink")
                                if soup.find(t)})
    res["flash"] = bool(re.search(r"\.swf\b|shockwave-flash", low))
    res["table_layout"] = len(soup.find_all("table")) >= 3 and not soup.find(["header", "nav", "footer"])
    res["mixed_content"] = https and bool(re.search(r'<(?:img|script|link)[^>]+(?:src|href)="http://', low))

    links = [a.get("href") or "" for a in soup.find_all("a")]
    socials = {}
    for h in links:
        k, lab = link_kind(h) if h.startswith("http") else ("", "")
        if k == "social" and lab not in socials and "sharer" not in h and "share?" not in h:
            socials[lab] = h
    res["socials_on_site"] = socials
    res["pdf_menu"] = any(h.lower().endswith(".pdf") and re.search(r"menu|food|drink|tariff|price", h, re.I)
                          for h in links)
    res["online_booking"] = any(b in low for b in BOOKING_HINTS)
    emails = {m.group(0).lower() for m in EMAIL_RE.finditer(" ".join(links) + " " + text)
              if not m.group(0).lower().endswith((".png", ".jpg", ".gif", ".webp", ".svg"))
              and "sentry" not in m.group(0) and "wixpress" not in m.group(0)
              and "example." not in m.group(0)}
    res["emails"] = sorted(emails)[:3]
    tels = [h[4:].strip() for h in links if h.lower().startswith("tel:")]
    res["phones"] = sorted(set(tels))[:2]
    res["contact_form"] = bool(soup.find("form") and soup.find("input", attrs={"type": "email"})) \
        or "contact" in " ".join(links).lower()
    res["free_builder"] = any(fb in final_dom for fb in FREE_BUILDER)
    res["internal_pages"] = len({urljoin(final_url, h).split("#")[0] for h in links
                                 if domain_of(urljoin(final_url, h)) == final_dom})
    return res


def archive_history(website: str) -> dict:
    """Internet Archive: when the site was first seen and when its homepage content last changed."""
    d = domain_of(website)
    if not d:
        return {}
    try:
        r = requests.get("https://web.archive.org/cdx/search/cdx",
                         params={"url": d, "output": "json", "fl": "timestamp,digest",
                                 "filter": "statuscode:200", "collapse": "digest"},
                         headers=UA, timeout=40)
        if r.status_code != 200 or not r.text.strip():
            return {}
        rows = r.json()[1:]
    except Exception:  # noqa: BLE001
        return {}
    if not rows:
        return {"archive_captures": 0}
    return {
        "archive_first": rows[0][0][:4],
        "archive_last_change": f"{rows[-1][0][:4]}-{rows[-1][0][4:6]}",
        "archive_versions": len(rows),
    }


def run_all(records: list[dict], log=print, discover_sectors=None, archive=True) -> None:
    for rec in records:
        classify_links(rec)

    todo = [r for r in records if not r.get("website")
            and (discover_sectors is None or r["sector"] in discover_sectors)]
    log(f"  looking for websites of {len(todo)} businesses with no website listed…")
    done = 0
    with ThreadPoolExecutor(config.AUDIT_WORKERS * 2) as ex:
        for _ in ex.map(discover, todo):
            done += 1
            if done % 250 == 0:
                log(f"    {done}/{len(todo)}")
    found = sum(1 for r in todo if r.get("website"))
    log(f"  found {found} extra websites")
    for rec in todo:
        if rec.get("website"):
            classify_links(rec)

    sites = [r for r in records if r.get("website")]
    log(f"  auditing {len(sites)} websites…")

    def _one(rec):
        try:
            rec["audit"] = audit(rec)
        except Exception as e:  # noqa: BLE001
            rec["audit"] = {"status": "error", "error": f"Audit failed ({type(e).__name__})", "issues": []}
        if archive:
            rec["audit"].update(archive_history(rec["website"]))
        return rec

    done = 0
    with ThreadPoolExecutor(config.AUDIT_WORKERS) as ex:
        for _ in ex.map(_one, sites):
            done += 1
            if done % 50 == 0:
                log(f"    {done}/{len(sites)}")

    rerender_thin(sites, log)


def rerender_thin(sites: list[dict], log=print) -> None:
    """Pages with almost no text in their raw HTML usually build their content with
    JavaScript (Wix, Squarespace, React…). Re-check those in a real browser."""
    thin = [r for r in sites if (r.get("audit") or {}).get("status") == "ok"
            and (r["audit"].get("words") or 0) < 150]
    if thin:
        log(f"  re-checking {len(thin)} JavaScript-heavy pages in a real browser…")
        rendered = render_pages([r["audit"]["final_url"] for r in thin], log)
        for r in thin:
            got = rendered.get(r["audit"]["final_url"]) or {}
            html = got.get("html") if isinstance(got, dict) else got
            if html:
                r["audit"].update(analyse(html, r["audit"]["final_url"], r["audit"]["https"]))
                r["audit"]["rendered"] = True


def render_pages(urls: list[str], log=print) -> dict[str, str]:
    """Render pages with the pre-installed Chromium (via Node Playwright). Returns {url: html}."""
    import json as _json
    import subprocess
    import tempfile
    script = os.path.join(os.path.dirname(__file__), "render.js")
    with tempfile.TemporaryDirectory() as tmp:
        inp = os.path.join(tmp, "in.json")
        out = os.path.join(tmp, "out.json")
        _json.dump(urls, open(inp, "w"))
        try:
            subprocess.run(["node", script, inp, out], check=True, timeout=60 + 25 * len(urls),
                           capture_output=True)
            return _json.load(open(out))
        except Exception as e:  # noqa: BLE001
            log(f"    browser check skipped ({type(e).__name__}); results use raw HTML only")
            return {}
