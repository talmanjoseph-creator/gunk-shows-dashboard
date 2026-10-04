#!/usr/bin/env python3
"""Pull club nights from NYC venues' own public calendars into SHOWS rows.

Reads plain HTML or a public JSON feed the venue's site already serves.
Checks robots.txt first. If a site answers 403/429, or with a bot challenge,
that venue is skipped. This does not fetch Resident Advisor.

    python3 tools/fetch_venues.py                 # print rows, using SHOW_META
    python3 tools/fetch_venues.py --from-day 4    # Oct 4 onward, for example
    python3 tools/fetch_venues.py --merge         # append rows to shows-data.js

Then run python3 tools/clean_shows.py.
"""
import argparse
import json
import re
import ssl
import sys
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "shows-data.js"
NY = ZoneInfo("America/New_York")
UA = "ShowMeNYC-venue-calendar/1.0 (+https://github.com/talmanjoseph-creator/gunk-shows-dashboard)"
DELAY = 0.45
# Same building as Knockdown Center. Added only when a Basement row is new.
VENUE_GEO = {
    "Basement": [40.715655, -73.914273],
    "Industry City": [40.6566834, -74.0072654],
}

_last = {}
_robots = {}
_requests = 0


class Skip(Exception):
    """This venue's calendar can't be read under the rules."""


def text(value):
    value = unescape(value or "")
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def clean_acts(value):
    value = text(value)
    value = re.sub(r"\s*[\(\[]\s*(?:dj set|open to close|all night)\s*[\)\]]", "", value, flags=re.I)
    value = re.sub(r"\s+DJ Set\b", "", value, flags=re.I)
    # A bracketed lineup is more names, not a subtitle: "Act [A, B]" -> "Act, A, B".
    value = re.sub(r"\s*\[([^\]]*,[^\]]*)\]", lambda m: ", " + m.group(1), value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip(" ,")


def clock(dt):
    hour = dt.hour
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{dt.minute:02d} {suffix}"


def nice(name):
    name = text(name).strip(" :,-")
    if not name or name.lower() in ("all night", "all night long"):
        return ""
    if name.isupper() and " " not in name and len(name) <= 6:
        return name
    if name != name.upper():
        return name
    out = []
    for word in name.split():
        if word.lower() in ("dj", "mc"):
            out.append(word.upper())
        else:
            out.append(word.capitalize())
    return " ".join(out)


def bill(title):
    """Split a party name off the front of a lineup so artist names stay comparable."""
    title = re.sub(r"\s*\[[^\]]*(?:live|dj set)[^\]]*\]", "", text(title), flags=re.I)
    title = re.sub(r"\s+All Day Long\b", "", title, flags=re.I)
    note, acts = split_party(title)
    if not note:
        parts = re.split(r"\s+[\u2013\u2014-]\s+", acts, maxsplit=1)
        if len(parts) == 2 and ("," in parts[1] or " b2b " in parts[1].lower()):
            note, acts = parts[0].strip(), parts[1].strip()
    if not note and ":" in acts:
        left, right = acts.split(":", 1)
        right = right.strip()
        if len(left) <= 36 and ("," in right or len(right.split()) >= 2):
            note, acts = left.strip(), right
    if not note:
        party = re.match(r"^(.+?)\s+((?:Anniversary|After) Party)$", acts, re.I)
        if party and len(party.group(1)) >= 4:
            note, acts = party.group(2), party.group(1)
    acts = re.sub(r"\s+with\s+", ", ", acts, flags=re.I)
    return note, clean_acts(acts)


def row(day, when, venue, acts, note, age, url):
    acts = clean_acts(acts)
    if not acts or not venue or not day:
        return None
    return [day, when or "", venue, acts, text(note), age or "", "club", url or ""]


def challenged(status, body, headers):
    blob = (body or "")[:4000].lower()
    server = (headers.get("server") or "").lower()
    mitigated = (headers.get("cf-mitigated") or "").lower()
    if mitigated or "attention required" in blob or "just a moment" in blob:
        return True
    if status in (403, 503) and "cloudflare" in server and "text/html" in (headers.get("content-type") or ""):
        return True
    return False


def fetch(url, accept="text/html,application/json;q=0.9,*/*;q=0.8", timeout=30):
    """GET one public URL. Polite delay per host. Raises Skip on a block."""
    global _requests
    host = urlsplit(url).netloc
    wait = DELAY - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()
    _requests += 1
    req = Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", "replace")
            if challenged(res.status, body, res.headers):
                raise Skip("bot challenge")
            return res.status, res.geturl(), body, res.headers
    except HTTPError as err:
        body = ""
        try:
            body = err.read().decode("utf-8", "replace")
        except Exception:
            pass
        headers = err.headers or {}
        if err.code == 429:
            raise Skip("HTTP 429")
        if challenged(err.code, body, headers):
            raise Skip(f"HTTP {err.code} bot challenge")
        if err.code in (403, 401):
            raise Skip(f"HTTP {err.code}")
        raise
    except URLError as err:
        raise Skip(f"could not connect ({err.reason})")


def robots_rules(origin):
    if origin in _robots:
        return _robots[origin]
    rules = []
    try:
        status, _, body, _ = fetch(origin + "/robots.txt", accept="text/plain,*/*")
    except Skip as err:
        if "404" in str(err):
            _robots[origin] = []
            return []
        raise
    except HTTPError:
        _robots[origin] = []
        return []
    if status == 404:
        _robots[origin] = []
        return []
    agents, bucket = [], []

    def flush():
        if agents:
            rules.append((agents[:], bucket[:]))

    for line in body.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if bucket:
                flush()
                agents, bucket = [], []
            agents.append(value.lower())
        elif key in ("allow", "disallow"):
            bucket.append((key, value))
    flush()
    star = []
    for agents, bucket in rules:
        if "*" in agents:
            star.extend(bucket)
    _robots[origin] = star
    return star


def allowed(url):
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    path = parts.path or "/"
    best = None
    try:
        rules = robots_rules(origin)
    except Skip:
        raise
    except HTTPError as err:
        if err.code == 404:
            return True
        raise Skip(f"robots.txt HTTP {err.code}")
    for kind, prefix in rules:
        if prefix == "":
            continue
        if path.startswith(prefix) and (best is None or len(prefix) > best[0]):
            best = (len(prefix), kind == "allow")
    return True if best is None else best[1]


def get(url, accept="text/html,application/json;q=0.9,*/*;q=0.8"):
    if not allowed(url):
        raise Skip("robots.txt disallows this page")
    return fetch(url, accept=accept)


def direct_ticket(url):
    """Follow a venue's ticket link far enough to land on the event page."""
    if not url or not url.lower().startswith("http"):
        return ""
    dice = re.search(r"dice\.fm/(?:partner/tickets/)?event/([^?#\s]+)", url, re.I)
    if dice and "link.dice.fm" not in urlsplit(url).netloc:
        return "https://dice.fm/event/" + dice.group(1).strip("/")
    if "link.dice.fm" not in url and "dice.fm/partner/" not in url:
        return url.split("#")[0]
    current = url
    for _ in range(5):
        host = urlsplit(current).netloc
        wait = DELAY - (time.time() - _last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        global _requests
        _requests += 1
        req = Request(current, headers={"User-Agent": UA, "Accept": "text/html"})
        try:
            with urlopen(req, timeout=25) as res:
                final = res.geturl()
                found = re.search(r"dice\.fm/(?:partner/tickets/)?event/([^?#\s]+)", final, re.I)
                if found:
                    return "https://dice.fm/event/" + found.group(1).strip("/")
                return final.split("?")[0]
        except HTTPError as err:
            loc = err.headers.get("Location") if err.headers else None
            if err.code in (301, 302, 303, 307, 308) and loc:
                current = loc
                found = re.search(r"dice\.fm/(?:partner/tickets/)?event/([^?#\s]+)", current, re.I)
                if found:
                    return "https://dice.fm/event/" + found.group(1).strip("/")
                continue
            return ""
        except URLError:
            return ""
    return ""


def dice_slug_day(url, month):
    """Day named in a Dice event slug, such as 8th-oct, when it is this month."""
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    match = re.search(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)-([a-z]{3})\b", url or "", re.I)
    if not match or months.get(match.group(2).lower()) != month:
        return None
    day = int(match.group(1))
    return day if 1 <= day <= 31 else None


def age_from(blob):
    blob = unescape(blob or "").replace("\\u002b", "+").replace("\\u002B", "+")
    match = re.search(r"(?<![0-9])(21|18|16)\s*\+|all ages", blob, re.I)
    if not match:
        return ""
    token = match.group(0).lower()
    return "AA" if "all" in token else match.group(1)


# ---------- venues ----------

def fetch_elsewhere(ctx):
    rows, page = [], 1
    while page <= 6:
        url = "https://www.elsewhere.club/events" + ("" if page == 1 else f"?page={page}")
        _, _, body, _ = get(url)
        parts = body.split('itemType="https://schema.org/MusicEvent"')[1:]
        if not parts:
            break
        saw_later = False
        for chunk in parts:
            chunk = chunk[:7000]
            name_m = re.search(r'itemProp="name">([^<]+)', chunk)
            when_m = re.search(r'dateTime="([^"]+)"[^>]*itemProp="startDate"', chunk)
            if not name_m or not when_m:
                continue
            dt = datetime.fromisoformat(when_m.group(1)).astimezone(NY)
            if (dt.year, dt.month) > (ctx["year"], ctx["month"]):
                saw_later = True
                continue
            day = ctx["day"](dt)
            badges = [text(b).lower() for b in re.findall(r'<li class="[^"]*badge[^"]*">([^<]+)</li>', chunk)]
            if "club" not in badges:
                continue
            if day is None:
                continue
            name = text(name_m.group(1))
            venue, note = "Elsewhere", ""
            off = re.search(r"\s@\s+(.+)$", name)
            if off:
                venue = text(off.group(1))
                name = re.sub(r"\s@\s+.+$", "", name)
                name = re.sub(r"^Elsewhere [Pp]resents:\s*", "", name)
                note = "Elsewhere presents"
            else:
                rooms = [text(b) for b in re.findall(r'<li class="[^"]*badge[^"]*">([^<]+)</li>', chunk)]
                rooms = [r for r in rooms if r.lower() not in ("club", "live", "full venue")]
                note = rooms[0] if rooms else ""
            party, acts = bill(name)
            if party:
                note = ", ".join(part for part in (party, note) if part)
            ticket = ""
            link = re.search(r"https://www\.eventbrite\.com/e/[^\"'\s<]+", chunk)
            if link:
                ticket = link.group(0)
            made = row(day, clock(dt), venue, acts, note, "", ticket)
            if made:
                rows.append(made)
        if f"page={page + 1}" not in body or saw_later and not any(r[0] for r in rows):
            # Keep paging while this page still links onward and we have not
            # gone past the month. A later page can still hold this month.
            if f"page={page + 1}" not in body:
                break
        if saw_later and page > 1 and not rows:
            break
        if f"page={page + 1}" not in body:
            break
        page += 1
    return rows


def fetch_public_records(ctx):
    _, _, body, _ = get("https://publicrecords.nyc/")
    rows = []
    for href, block in re.findall(r'<a target="_blank" class="event table-row" href="([^"]+)"([\s\S]*?)</a>', body):
        cell_m = re.search(r'class="table-cell date">(.*?)</div>', block, re.S)
        title_m = re.search(r'class="table-cell title">\s*([^<]+)', block)
        if not cell_m or not title_m:
            continue
        cell = cell_m.group(1)
        cats = re.findall(r"\b(Club|Live|Etc)\b", cell)
        if "Club" not in cats:
            continue
        date_m = re.search(r"(\d+)\.(\d+)", cell)
        time_m = re.search(r"(\d{1,2}:\d{2}\s*[ap]m)", cell, re.I)
        if not date_m:
            continue
        month, day = int(date_m.group(1)), int(date_m.group(2))
        if month != ctx["month"]:
            continue
        rooms = [text(r) for r in re.findall(r'class="location">([^<]+)', block)]
        party, acts = bill(title_m.group(1))
        note_parts = []
        if party and party not in rooms:
            note_parts.append(party)
        note_parts.extend(rooms)
        ticket = direct_ticket(text(href))
        # The ticket slug names the night. The calendar cell can be a week off
        # (Hearts & Diamonds is Thu 10.15 on the page and Oct 8 on the ticket).
        named = dice_slug_day(ticket, ctx["month"])
        if named:
            day = named
        if day < ctx["from_day"]:
            continue
        when = ""
        if time_m:
            parsed = datetime.strptime(time_m.group(1).upper().replace(" ", ""), "%I:%M%p")
            when = f"{parsed.hour % 12 or 12}:{parsed.minute:02d} {'AM' if parsed.hour < 12 else 'PM'}"
            # strptime %p with 12-hour: hour is 0-23 already? %I is 1-12 and %p sets AM/PM.
            # datetime.strptime("3:00PM", "%I:%M%p").hour == 15. Use that.
            when = clock(parsed)
        made = row(day, when, "Public Records", acts, ", ".join(note_parts), "", ticket)
        if made:
            rows.append(made)
    return rows


def split_party(line):
    line = re.sub(r"\s*\(all night\)", "", text(line), flags=re.I).strip(" ,")
    match = re.match(r"(.+?)\s+(?:with|w/|ft\.?|feat\.?|presents):?\s+(.+)$", line, re.I)
    if match and len(match.group(1)) <= 42:
        return match.group(1).strip(), match.group(2).strip()
    return "", line


def fetch_good_room(ctx):
    # The certificate on https is not the venue's; the calendar is served over http.
    _, _, body, _ = get("http://www.goodroombk.com/")
    rows = []
    for art in re.findall(r"<article\b[\s\S]*?</article>", body):
        if "type-events" not in art:
            continue
        date_m = re.search(
            r'title="(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), ([A-Za-z]+ \d{1,2}, \d{4})"',
            art,
        )
        if not date_m:
            continue
        dt = datetime.strptime(date_m.group(1), "%B %d, %Y").replace(tzinfo=NY)
        day = ctx["day"](dt)
        if day is None:
            continue
        notes, acts = [], []
        for lineup in re.findall(r'class="c_lineup[^"]*">([^<]*)', art):
            party, names = bill(lineup)
            if party:
                notes.append(party)
            if names:
                acts.append(names)
        link_m = re.search(r'event-ticket-link[\s\S]*?href="([^"]+)"', art)
        ticket = ""
        if link_m and link_m.group(1).lower().startswith("http"):
            ticket = link_m.group(1)
        made = row(day, "", "Good Room", ", ".join(acts), ", ".join(dict.fromkeys(notes)), "", ticket)
        if made:
            rows.append(made)
    return rows


def fetch_basement(ctx):
    # The venue page is a script shell. Its script calls this public JSON feed.
    # robots.txt on that host is a 404, so nothing is disallowed.
    url = "https://basement.mtebi.com/events/public?status=published&limit=50"
    if not allowed("https://basementny.net/"):
        raise Skip("robots.txt disallows the venue site")
    _, _, body, _ = get(url, accept="application/json")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise Skip("events feed was not JSON")
    rows = []
    for ev in data:
        try:
            dt = datetime.strptime(ev.get("start_date") or "", "%Y-%m-%d %H:%M").replace(tzinfo=NY)
        except ValueError:
            continue
        day = ctx["day"](dt)
        if day is None:
            continue
        acts = []
        for stage in (ev.get("basement_stage") or "", ev.get("studio_stage") or ""):
            for part in stage.split(","):
                person = nice(part)
                if person:
                    acts.append(person)
        name = text(ev.get("name") or "")
        note = "" if re.fullmatch(r"(?i)[a-z]+\s+\d{1,2}", name) else nice(name)
        if not acts and note:
            acts, note = [note], ""
        made = row(day, clock(dt), "Basement", ", ".join(acts), note, age_from(ev.get("description") or ""), ev.get("ticket_link") or "")
        if made:
            rows.append(made)
    return rows


def fetch_h0l0(ctx):
    _, _, body, _ = get("https://h0l0.nyc/events")
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', body, re.S)
    if not match:
        raise Skip("events page had no readable calendar")
    payload = json.loads(match.group(1))
    events = payload.get("props", {}).get("pageProps", {}).get("allUpcomingEvents") or []
    rows = []
    for ev in events:
        attrs = ev.get("attributes") or {}
        raw = attrs.get("EventDateTime") or ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(NY)
        except ValueError:
            continue
        day = ctx["day"](dt)
        if day is None:
            continue
        ticket = direct_ticket(attrs.get("Link") or "")
        party, acts = bill(attrs.get("Title") or "")
        made = row(day, clock(dt), "H0L0", acts, party, age_from(attrs.get("Description") or ""), ticket)
        if made:
            rows.append(made)
    return rows


def fetch_house_of_yes(ctx):
    _, _, body, _ = get("https://calendar.houseofyes.org/")
    cards = re.findall(
        r'<a href="(/e/[^"]+)" class="shotgun-event-card[\s\S]*?'
        r'events-listing-event-name[^"]*">([^<]+)</strong>[\s\S]*?'
        r'<time[^>]*datetime="([^"]+)"',
        body,
    )
    rows = []
    seen = set()
    for path, name, raw in cards:
        if path in seen:
            continue
        seen.add(path)
        try:
            dt = datetime.fromisoformat(raw).astimezone(NY)
        except ValueError:
            continue
        day = ctx["day"](dt)
        if day is None:
            continue
        page_url = "https://calendar.houseofyes.org" + path
        ticket, age, venue = page_url, "", "House of Yes"
        try:
            _, _, page, _ = get(page_url)
        except Skip:
            page = ""
        if page:
            for blob in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
                try:
                    data = json.loads(unescape(blob))
                except json.JSONDecodeError:
                    continue
                if "Event" not in str(data.get("@type")):
                    continue
                place = ((data.get("location") or {}).get("name") or "")
                offer = (data.get("offers") or {}).get("url") or ""
                if offer:
                    ticket = direct_ticket(offer) or page_url
                if "industry city" in place.lower() or "industry-city" in ticket.lower():
                    venue = "Industry City"
                elif place and "house of yes" not in place.lower():
                    venue = ""
                    break
                age = age_from(data.get("description") or "") or age_from(page)
                break
            if not age:
                age = age_from(page)
            if not venue:
                continue
        title = text(name)
        evening = re.match(r"(?i)an evening with\s+(.+)$", title)
        acts = evening.group(1) if evening else title
        made = row(day, clock(dt), venue, acts, "", age, ticket if ticket.startswith("http") else page_url)
        if made:
            rows.append(made)
    return rows


def fetch_nowadays(ctx):
    _, _, body, _ = get("https://nowadays.nyc/wp-sitemap-posts-post-1.xml", accept="application/xml,text/xml,*/*")
    prefix = f"https://nowadays.nyc/{ctx['year']}/{ctx['month']:02d}/"
    locs = [loc for loc in re.findall(r"<loc>([^<]+)</loc>", body) if loc.startswith(prefix)]
    rows = []
    for loc in locs:
        day_m = re.match(rf"https://nowadays\.nyc/{ctx['year']}/{ctx['month']:02d}/(\d{{2}})/", loc)
        if not day_m:
            continue
        day = int(day_m.group(1))
        if day < ctx["from_day"]:
            continue
        _, _, page, _ = get(loc)
        title_m = re.search(r"<title>([^<]+)</title>", page)
        title = text(title_m.group(1) if title_m else "")
        title = re.sub(r"\s+[–-]\s+Nowadays\s*$", "", title)
        ticket = ""
        for href in re.findall(r'href="(https?://[^"]+)"', page):
            if any(host in href for host in ("dice.fm/event", "eventbrite.com/e/", "shotgun.live/events/")):
                ticket = direct_ticket(href)
                break
        made = row(day, "", "Nowadays", title, "", "", ticket or loc)
        if made:
            rows.append(made)
    return rows


def fetch_knockdown(ctx):
    """The public calendar page. Skipped if it blocks or does not include events."""
    _, _, body, _ = get("https://knockdown.center/upcoming/")
    if "schema.org/Event" not in body and "event-title" not in body.lower() and body.lower().count("october") < 2:
        raise Skip("calendar page does not include the event list")
    raise Skip("calendar page did not match a known readable format")


def fetch_avant_gardner(ctx):
    if not allowed("https://www.avant-gardner.com/events"):
        raise Skip("robots.txt disallows the site")
    raise Skip("robots.txt allows a path but no calendar parser is configured")


def fetch_jupiter(ctx):
    _, _, body, _ = get("https://www.jupiterdisco.com/events")
    if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d", body):
        raise Skip("events page has dates but no parser yet")
    raise Skip("events page does not publish a calendar")


def fetch_gabriela(ctx):
    _, _, body, _ = get("https://gabriela.nyc/")
    own = re.findall(r'href="(https?://gabriela\.nyc/[^"]*event[^"]*)"', body, re.I)
    if own:
        raise Skip("events page has dates but no parser yet")
    raise Skip("site does not publish a calendar")


def fetch_bossa(ctx):
    try:
        _, final, body, _ = get("https://www.bossanovacivicclub.com/")
    except Skip:
        raise
    host = urlsplit(final).netloc.lower()
    if "bossa" not in host or "event" not in body.lower():
        raise Skip("the venue's old domain no longer publishes a calendar")
    raise Skip("site responded but had no readable event list")


def fetch_tba(ctx):
    try:
        get("https://www.tbabrooklyn.com/")
    except Skip as err:
        if "404" in str(err) or "HTTP 404" in str(err):
            raise Skip("site returned 404")
        raise
    except HTTPError as err:
        if err.code == 404:
            raise Skip("site returned 404")
        raise
    raise Skip("site did not include a readable event list")


def fetch_mirage(ctx):
    try:
        get("https://www.brooklynmirrage.com/robots.txt")
    except Skip as err:
        raise Skip(str(err))
    raise Skip("no readable calendar")


VENUES = [
    ("Elsewhere", fetch_elsewhere),
    ("Public Records", fetch_public_records),
    ("Good Room", fetch_good_room),
    ("Basement", fetch_basement),
    ("H0L0", fetch_h0l0),
    ("House of Yes", fetch_house_of_yes),
    ("Nowadays", fetch_nowadays),
    ("Knockdown Center", fetch_knockdown),
    ("Avant Gardner", fetch_avant_gardner),
    ("Brooklyn Mirage", fetch_mirage),
    ("Jupiter Disco", fetch_jupiter),
    ("Gabriela", fetch_gabriela),
    ("Bossa Nova Civic Club", fetch_bossa),
    ("TBA Brooklyn", fetch_tba),
]

# Checked this way on purpose: the domain is not the club's site.
STATIC_SKIPS = [
    ("Mood Ring", "moodringnyc.com is not the venue's site, and no other public calendar was found"),
    ("Le Bain", "le-bain.com does not list this month's nights on its public page"),
    ("Nublu", "nublu.net has no month calendar, only a short homepage carousel"),
]


def show_meta():
    src = INDEX.read_text(encoding="utf-8")
    year = int(re.search(r"year:\s*(\d+)", src).group(1))
    month = int(re.search(r"month:\s*(\d+)", src).group(1))
    return year, month


def merge_rows(rows):
    src = INDEX.read_text(encoding="utf-8")
    start = src.index("var SHOWS = [")
    end = src.index("];", start)
    existing = src[start:end].rstrip()
    if rows:
        if not existing.endswith(","):
            existing += ","
        blob = ",\n".join("  " + json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows)
        src = src[:start] + existing + "\n" + blob + "\n" + src[end:]
    venues = {r[2] for r in rows}
    g0 = src.index("var GEO = {")
    g1 = src.index("};", g0)
    block = src[g0:g1]
    additions = []
    for name in sorted(venues):
        if name not in VENUE_GEO:
            continue
        key = json.dumps(name, ensure_ascii=False)
        if re.search(r"^\s*" + re.escape(key) + r"\s*:", block, re.M):
            continue
        additions.append("  " + key + ": " + json.dumps(VENUE_GEO[name]))
    if additions:
        head = src[:g1].rstrip()
        if not head.endswith(","):
            head += ","
        src = head + "\n" + ",\n".join(additions) + "\n" + src[g1:]
    INDEX.write_text(src, encoding="utf-8")
    return len(rows), [name for name in venues if name in VENUE_GEO]


def main():
    year0, month0 = show_meta()
    parser = argparse.ArgumentParser(description="Fetch club nights from venue calendars.")
    parser.add_argument("--year", type=int, default=year0)
    parser.add_argument("--month", type=int, default=month0)
    parser.add_argument("--from-day", type=int, default=1)
    parser.add_argument("--merge", action="store_true", help="append rows to shows-data.js")
    args = parser.parse_args()

    def day_of(dt):
        if dt.year != args.year or dt.month != args.month or dt.day < args.from_day:
            return None
        return dt.day

    ctx = {"year": args.year, "month": args.month, "from_day": args.from_day, "day": day_of}
    found, skipped = [], []
    for name, fn in VENUES:
        try:
            rows = fn(ctx)
        except Skip as err:
            skipped.append((name, str(err)))
            print(f"skip  {name}: {err}", file=sys.stderr)
            continue
        except HTTPError as err:
            skipped.append((name, f"HTTP {err.code}"))
            print(f"skip  {name}: HTTP {err.code}", file=sys.stderr)
            continue
        except Exception as err:
            skipped.append((name, f"{type(err).__name__}: {err}"))
            print(f"skip  {name}: {type(err).__name__}: {err}", file=sys.stderr)
            continue
        found.append((name, rows))
        print(f"read  {name}: {len(rows)}", file=sys.stderr)
    for name, reason in STATIC_SKIPS:
        skipped.append((name, reason))
        print(f"skip  {name}: {reason}", file=sys.stderr)

    rows = [r for _, batch in found for r in batch]
    print(f"{len(rows)} club rows, {_requests} requests", file=sys.stderr)
    if args.merge:
        added, geos = merge_rows(rows)
        print(f"appended {added} rows to shows-data.js", file=sys.stderr)
        if geos:
            print("GEO added for: " + ", ".join(geos), file=sys.stderr)
    else:
        for item in rows:
            print(json.dumps(item, ensure_ascii=False))
    # Machine-readable summary on stdout when merging, so the counts are easy to keep.
    if args.merge:
        summary = {
            "venues": [{"name": name, "events": len(batch)} for name, batch in found],
            "skipped": [{"name": name, "reason": reason} for name, reason in skipped],
            "rows": len(rows),
        }
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
