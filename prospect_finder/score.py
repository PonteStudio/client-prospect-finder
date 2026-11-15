"""Turn the raw data into: online-presence status, findings (with why each matters), services
to pitch, and a 0–100 priority score."""
from __future__ import annotations

import datetime as dt
import re

from . import config
from .geo import haversine_km

THIS_YEAR = dt.date.today().year

# How valuable a client of this kind usually is (0–1). Rough, editable.
CATEGORY_VALUE = {
    "hotel": 1.0, "hotel / b&b": 0.9, "guest house": 0.8, "hostel": 0.7, "motel": 0.7,
    "camp site": 0.8, "caravan site": 0.8, "apartment": 0.6, "chalet": 0.6,
    "restaurant": 0.85, "restaurant / café": 0.75, "pub": 0.8, "pub / bar": 0.8, "bar": 0.7,
    "cafe": 0.65, "biergarten": 0.6, "nightclub": 0.6, "ice cream": 0.5,
    "takeaway": 0.45, "fast food": 0.45, "mobile caterer": 0.4, "other catering": 0.25,
    "food & drink shop": 0.5, "food producer": 0.6, "farm": 0.5,
}
SECTOR_VALUE = {
    "Hospitality": 0.75, "Leisure & Attractions": 0.75, "Health & Beauty": 0.6,
    "Professional services": 0.6, "Trades & Home": 0.6, "Retail": 0.5, "Automotive": 0.55,
    "Food production": 0.55, "Other": 0.3,
}

# (issue key, points, finding text, why it matters, service)
SITE_CHECKS = [
    ("placeholder", 40, "Website is a placeholder / 'coming soon' / parked page",
     "They have a domain but no real site – easy to show the gap", "Website"),
    ("free_builder", 12, "Site runs on a free-builder subdomain",
     "Looks unprofessional and they don't own the address", "Website, Branding"),
    ("no_https", 14, "No HTTPS – browsers mark it 'Not secure'",
     "Puts visitors off and Google ranks insecure sites lower", "Website, SEO"),
    ("no_viewport", 16, "Not built for mobile (no responsive layout)",
     "Most local searches happen on phones; Google ranks mobile-unfriendly sites lower", "Website"),
    ("old_copyright", 8, "Footer copyright year is old",
     "A visible sign the site hasn't been looked after", "Website"),
    ("stale_archive", 8, "Homepage content hasn't changed in years (Internet Archive)",
     "Out-of-date info (menus, prices, hours) costs bookings", "Website, Consulting"),
    ("old_tech", 8, "Old technology in use",
     "Old code is slower, less secure and harder to update", "Website"),
    ("no_title", 6, "Page has no proper title",
     "The title is what Google shows as the headline – a basic SEO miss", "SEO"),
    ("no_meta", 4, "No meta description",
     "Google writes its own snippet, often badly – easy SEO win", "SEO"),
    ("no_h1", 3, "No main heading (H1)", "Weaker SEO and harder to scan", "SEO"),
    ("alt_missing", 5, "Many images without alt text",
     "Fails accessibility for screen-reader users and loses image-search traffic", "Website, SEO"),
    ("zoom_blocked", 3, "Page blocks zooming on mobile", "Accessibility failure for low-vision users", "Website"),
    ("no_lang", 2, "Page language not declared", "Accessibility/SEO basic", "Website"),
    ("no_schema", 3, "No local-business structured data",
     "Helps Google show hours, address and reviews in results", "SEO, Google Business Profile"),
    ("pdf_menu", 5, "Menu / prices only as a PDF",
     "PDFs are hard to read on phones and invisible to Google", "Website, SEO"),
    ("no_booking", 4, "No online booking found",
     "Direct bookings avoid OTA commission (Booking.com takes ~15%+)", "Website, Landing page"),
    ("no_social_links", 2, "Website doesn't link to any social media",
     "Missed chance to connect channels", "Social media"),
    ("no_contact", 4, "No email/phone/contact form visible on homepage",
     "Visitors who want to book or ask can't easily get in touch", "Website"),
    ("slow", 5, "Slow to respond / heavy homepage",
     "Visitors leave slow sites; speed is a ranking factor", "Website"),
    ("thin", 6, "Very little content (single thin page)",
     "Nothing for Google to rank and little to persuade visitors", "Website, SEO"),
    ("mixed", 3, "Insecure content on a secure page", "Browser warnings / broken padlock", "Website"),
]
SITE_MAX = 50  # issue points that count as 'maximum need'


def site_issues(rec: dict) -> list[str]:
    a = rec.get("audit") or {}
    cat = (rec.get("category") or "").lower()
    s = []
    if a.get("placeholder"):
        s.append("placeholder")
    if a.get("free_builder"):
        s.append("free_builder")
    if not a.get("https"):
        s.append("no_https")
    if not a.get("viewport"):
        s.append("no_viewport")
    cy = a.get("copyright_year")
    if cy and cy <= THIS_YEAR - 3:
        s.append("old_copyright")
    lc = a.get("archive_last_change")
    if lc and int(lc[:4]) <= THIS_YEAR - 4:
        s.append("stale_archive")
    jq = a.get("jquery") or ""
    if a.get("flash") or a.get("old_markup") or a.get("table_layout") or \
            (jq and tuple(int(x) for x in jq.split(".")[:2]) < (1, 12)):
        s.append("old_tech")
    if not a.get("title"):
        s.append("no_title")
    if not a.get("meta_description"):
        s.append("no_meta")
    if a.get("h1", 0) == 0:
        s.append("no_h1")
    if a.get("images", 0) >= 3 and a.get("images_no_alt", 0) / a["images"] > 0.3:
        s.append("alt_missing")
    if a.get("zoom_blocked"):
        s.append("zoom_blocked")
    if not a.get("lang"):
        s.append("no_lang")
    if not a.get("schema_local_business"):
        s.append("no_schema")
    hosp = rec["sector"] == "Hospitality"
    if hosp and a.get("pdf_menu"):
        s.append("pdf_menu")
    if hosp and not a.get("online_booking") and any(
            k in cat for k in ("hotel", "b&b", "guest", "hostel", "camp", "caravan", "restaurant",
                               "apartment", "chalet")):
        s.append("no_booking")
    if not a.get("socials_on_site"):
        s.append("no_social_links")
    if not (a.get("emails") or a.get("phones") or a.get("contact_form")):
        s.append("no_contact")
    if (a.get("load_seconds") or 0) > 4 or (a.get("html_kb") or 0) > 1500:
        s.append("slow")
    if (a.get("words") or 0) < 120 and (a.get("internal_pages") or 0) < 4:
        s.append("thin")
    if a.get("mixed_content"):
        s.append("mixed")
    return s


def _dedupe_phones(raw: list[str]) -> list[str]:
    out, seen = [], set()
    for p in raw:
        d = re.sub(r"\D", "", p)
        if d.startswith("44"):
            d = "0" + d[2:]
        if len(d) < 9 or d in seen:
            continue
        seen.add(d)
        out.append(f"{d[:5]} {d[5:]}" if len(d) == 11 else d)
    return out


def presence(rec: dict) -> str:
    a = rec.get("audit")
    socials = rec.get("socials") or {}
    if rec.get("website") and a:
        if a.get("status") == "error":
            return "Website not working"
        if a.get("status") == "no_https":
            return "Website – no secure version"
        if a.get("status") == "blocked":
            return "Website (could not check)"
        if a.get("status") == "blocked":
            return "Website (could not check)"
        if a.get("placeholder"):
            return "Placeholder website"
        if a.get("final_url"):
            from .websites import link_kind
            kind, _ = link_kind(a["final_url"])
            if kind == "social":
                return "Social media only"
            if kind == "listing":
                return "Listing pages only"
        return "Has website"
    if socials:
        return "Social media only"
    if rec.get("listings"):
        return "Listing pages only"
    return "No website found"


def evaluate(rec: dict, centre: tuple[float, float], radius_km: float) -> None:
    w = config.WEIGHTS
    a = rec.get("audit") or {}
    rec["distance_km"] = round(haversine_km(centre[0], centre[1], rec["lat"], rec["lon"]), 1)
    rec["presence"] = presence(rec)
    findings: list[str] = []
    services: set[str] = set()

    # ---------------- opportunity
    p = rec["presence"]
    issues: list[str] = []
    confidence = "High"
    ver = rec.get("verified") or {}
    if ver:
        confidence = f"Checked by hand {ver.get('date','')}".strip()
    if p == "No website found":
        both = len(rec["sources"]) > 1
        if ver.get("no_website"):
            opp = 0.85
            findings.append("No website – confirmed by a manual web search")
        else:
            opp = 0.72 if both else 0.62
            confidence = "Medium – not in OpenStreetMap or found by domain search; verify" if both else \
                "Low – only in the hygiene register, no web data; verify before contacting"
            findings.append("No website found – " + (
                "not listed on OpenStreetMap and no matching domain found" if both else
                "no matching domain found (OpenStreetMap has no entry for them)"))
        findings.append("Why it matters: without a site they rely on third parties and are hard to "
                        "find on Google – the strongest case for a website + Google Business Profile")
        services |= {"Website", "Google Business Profile", "Branding"}
    elif p == "Social media only":
        opp = 0.92
        nets = ", ".join(sorted((rec.get("socials") or {}).keys())) or a.get("redirects_to", "")
        findings.append(f"Only on social media ({nets}) – no website of their own")
        findings.append("Why it matters: social posts don't rank on Google and they don't own "
                        "the channel; an active social presence shows they care about being found")
        services |= {"Website", "Landing page", "Google Business Profile"}
    elif p == "Listing pages only":
        opp = 0.85
        findings.append("Only appears on directory/booking listings: " + ", ".join(
            sorted({l.split('/')[2] if '//' in l else l
                       for l in (rec.get('listings') or [a.get('final_url') or rec.get('website', '')])}))[:120])
        findings.append("Why it matters: paying commission/fees to third parties for every "
                        "customer; a direct site keeps the margin")
        services |= {"Website", "Google Business Profile", "SEO"}
    elif p == "Website not working":
        opp = 0.95
        findings.append(f"Website listed ({rec['website']}) but not working: {a.get('error')}")
        findings.append("Why it matters: customers who click get an error – urgent, easy to explain")
        services |= {"Website", "Consulting"}
    elif p == "Website (could not check)":
        opp = 0.25
        confidence = "Low – site does not allow automated checks; look at it by hand"
        findings.append(f"Has a website ({rec['website']}) that does not allow automated checks – look manually")
    elif p == "Website – no secure version":
        opp = 0.75
        confidence = "Medium – open the site to confirm it loads"
        findings.append(f"Website ({rec['website']}) has no working secure (https) version – "
                        "browsers show 'Not secure' or the site is down")
        findings.append("Why it matters: Chrome warns visitors away from insecure sites and Google "
                        "ranks them lower; usually a sign the whole site is dated")
        services |= {"Website", "SEO"}
    elif p == "Website (could not check)":
        opp = 0.25
        confidence = "Low – site does not allow automated checks; look at it by hand"
        findings.append(f"Has a website ({rec['website']}) that does not allow automated checks – look manually")
    elif p == "Placeholder website":
        opp = 0.9
        findings.append("Website is just a placeholder / 'coming soon' page")
        services |= {"Website", "Branding"}
    else:
        issues = site_issues(rec)
        pts = 0
        for key, points, text, why, svc in SITE_CHECKS:
            if key in issues:
                pts += points
                extra = ""
                if key == "old_copyright":
                    extra = f" ({a.get('copyright_year')})"
                elif key == "stale_archive":
                    extra = f" (last change {a.get('archive_last_change')})"
                elif key == "old_tech":
                    bits = []
                    if a.get("jquery"):
                        bits.append(f"jQuery {a['jquery']}")
                    if a.get("old_markup"):
                        bits.append("<" + ">, <".join(a["old_markup"]) + "> tags")
                    if a.get("flash"):
                        bits.append("Flash")
                    if a.get("table_layout"):
                        bits.append("table-based layout")
                    extra = f" ({', '.join(bits)})" if bits else ""
                elif key == "slow":
                    extra = f" ({a.get('load_seconds')}s, {a.get('html_kb')} KB HTML)"
                findings.append(f"{text}{extra} – {why}")
                services |= {s.strip() for s in svc.split(",")}
        opp = min(pts, SITE_MAX) / SITE_MAX * 0.85
        if not findings:
            findings.append("Website looks in reasonable shape on automated checks")
    if ver.get("notes"):
        findings.append("Note from manual check: " + ver["notes"])
    # Social-but-no-site extras
    if not rec.get("socials") and not (a.get("socials_on_site")) and p != "No website found":
        services.add("Social media")

    # ---------------- distance
    dist_score = max(0.0, 1 - rec["distance_km"] / max(radius_km, 1))

    # ---------------- strength / size (rough, open data only)
    cat = (rec.get("category") or "").lower()
    strength = CATEGORY_VALUE.get(cat, SECTOR_VALUE.get(rec["sector"], 0.4))
    tags = rec.get("osm_tags") or {}
    if tags.get("stars") or tags.get("rooms"):
        strength = min(1.0, strength + 0.1)
    if a.get("archive_first") and int(a["archive_first"]) <= THIS_YEAR - 10:
        strength = min(1.0, strength + 0.05)  # long-established

    # ---------------- contactability
    emails = sorted(set(([rec["email"]] if rec.get("email") else []) + (a.get("emails") or [])))
    phones = _dedupe_phones(([rec["phone"]] if rec.get("phone") else []) + (a.get("phones") or []))
    socials = dict(a.get("socials_on_site") or {})
    socials.update(rec.get("socials") or {})
    rec["all_emails"], rec["all_phones"], rec["all_socials"] = emails, phones, socials
    contact = (0.45 if emails else 0) + (0.3 if phones else 0) + (0.25 if socials else 0)

    parts = {
        "opportunity": opp * w["opportunity"],
        "distance": dist_score * w["distance"],
        "strength": strength * w["strength"],
        "contactability": contact * w["contactability"],
    }
    rec["score"] = round(sum(parts.values()))
    if ver.get("exclude"):
        # Hand-checked and ruled out (closed, chain, for sale…): keep the row, sink it.
        rec["score"] = 0
        findings.insert(0, "EXCLUDED after manual check: " + ver["exclude"])
    rec["score_parts"] = {k: round(v) for k, v in parts.items()}
    rec["findings"] = findings
    rec["issues"] = issues
    rec["services"] = sorted(services)
    rec["confidence"] = confidence
    rec["core_market"] = rec["sector"] == config.CORE_SECTOR

    if emails:
        best = "Email"
    elif socials.get("instagram") or socials.get("facebook"):
        best = "Social media DM (" + ", ".join(k for k in ("facebook", "instagram") if k in socials) + ")"
    elif phones:
        best = "Phone"
    else:
        best = "Visit in person / find contact"
    rec["best_contact"] = best
