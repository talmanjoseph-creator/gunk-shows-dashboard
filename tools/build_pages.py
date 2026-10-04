#!/usr/bin/env python3
"""Generate a page for every show and every venue from shows-data.js.

    python3 tools/build_pages.py

Writes shows/<slug>.html, venues/<slug>.html and sitemap.xml.
tools/clean_shows.py runs this automatically after cleaning the data.

Show pages are permanent links. Only the pages for the month in
shows-data.js are rebuilt (so a cancelled show's page disappears); pages
from earlier months are left exactly where they are, and their "already
happened" note is switched on by pages.js from the date on the page.
Venue pages are rewritten for every venue in the current data; a venue page
with no shows this month is left in place so older show pages still link.

The show slug is built from the row alone (full date, venue, first act,
time), with -2, -3 ... added when two rows would share a name, in list
order. index.html computes the same slug in the browser to link each row,
so if you change the rules here, change showSlug() and the slug loop in
index.html to match.
"""
import html
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, quote_plus

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    NY = None

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "shows-data.js"
SITE = "https://talmanjoseph-creator.github.io/gunk-shows-dashboard/"

DAY, TIME, VENUE, ACTS, NOTE, AGE, SRC, URL = range(8)
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
AREA_NAME = {
    "bush": "Bushwick / Ridgewood", "wbg": "Williamsburg / Greenpoint",
    "bk": "Rest of Brooklyn", "les": "Manhattan below 14th",
    "mid": "Manhattan above 14th", "qns": "Queens",
    "bx": "Bronx / Staten Island", "out": "Out of town",
}
# Words in a bill that are not an act worth a listen link.
NOT_AN_ACT = re.compile(r"^(special guests?|guests?|friends|tbd|tba|more|and more|\+ ?more|& ?more|djs?)$", re.I)

esc = lambda s: html.escape(str(s), quote=True)


# ---------- reading shows-data.js ----------
def js_block(src, name, opener, closer):
    start = src.index(f"var {name} = {opener}") + len(f"var {name} = ")
    end = src.index(f"\n{closer};", start) + 1 + len(closer)
    return src[start:end]


def load():
    src = DATA.read_text(encoding="utf8")
    shows = json.loads(re.sub(r",\s*\]$", "]", js_block(src, "SHOWS", "[", "]").strip()))
    geo = json.loads(js_block(src, "GEO", "{", "}"))
    area = json.loads(js_block(src, "AREA", "{", "}"))
    year = int(re.search(r"\byear:\s*(\d+)", src).group(1))
    month = int(re.search(r"\bmonth:\s*(\d+)", src).group(1))
    gunk_url = re.search(r"gunk:\s*\{.*?url:\s*\"([^\"]+)\"", src, re.S).group(1)
    other = re.search(r"other:\s*\{(.*?)\}", src, re.S).group(1)
    other_name = re.search(r"name:\s*\"([^\"]+)\"", other).group(1)
    other_url = re.search(r"url:\s*\"([^\"]+)\"", other).group(1)
    return shows, geo, area, year, month, gunk_url, other_name, other_url


# ---------- slugs (keep in step with showSlug() / slugify() in index.html) ----------
def slugify(text):
    import unicodedata
    t = unicodedata.normalize("NFD", text.lower())
    t = re.sub("[\u0300-\u036f'\u2019]", "", t)  # accents and apostrophes: "Baby's" -> "babys"
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def part(text, n):
    return slugify(text)[:n].strip("-") or "x"


def time_slug(t):
    m = re.match(r"(\d+):(\d+)\s*(AM|PM)", t or "", re.I)
    return f"{int(m[1])}{m[2]}{m[3].lower()}" if m else "tba"


def show_slug(s, year, month):
    return "-".join([
        f"{year}-{month:02d}-{s[DAY]:02d}",
        part(s[VENUE], 30), part(s[ACTS].split(",")[0], 30), time_slug(s[TIME]),
    ])


def unique_slugs(shows, year, month):
    """One slug per row, in list order; repeats get -2, -3, ... (same rule as index.html)."""
    count, out = {}, []
    for s in shows:
        base = show_slug(s, year, month)
        count[base] = count.get(base, 0) + 1
        out.append(base if count[base] == 1 else f"{base}-{count[base]}")
    return out


def legacy_slug(s, month):
    """The first scheme, live for part of Oct 4, 2026: no year, month by name."""
    return "-".join([
        MONTHS[month - 1][:3].lower(), f"{s[DAY]:02d}",
        part(s[VENUE], 30), part(s[ACTS].split(",")[0], 30), time_slug(s[TIME]),
    ])


# Months whose pages were first published under legacy_slug(); their old
# addresses keep working through small redirect pages.
LEGACY_MONTHS = {(2026, 10)}


def venue_slug(name):
    return part(name, 50)


# ---------- small helpers ----------
def minutes(t):
    m = re.match(r"(\d+):(\d+)\s*(AM|PM)", t or "", re.I)
    if not m:
        return None
    return int(m[1]) % 12 * 60 + (720 if m[3].upper() == "PM" else 0) + int(m[2])


def sort_key(s):
    m = minutes(s[TIME])
    if m is None:
        return (s[DAY], 99999)
    return (s[DAY], m + 1440 if m < 300 else m)  # before 5 AM = late night


def age_label(a):
    return "All ages" if a == "AA" else (a + "+" if a else "")


def map_url(venue, area):
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(
        venue + ("" if area == "out" else ", New York, NY"))


def act_names(acts):
    """Individual acts from a bill, for the listen links."""
    out = []
    for piece in acts.split(","):
        piece = re.sub(r"\(.*?\)", "", piece)
        if ": " in piece:
            piece = piece.split(": ")[-1]
        piece = re.sub(r"\s+(\+|&)\s*more$", "", piece.strip(), flags=re.I).strip(" .")
        if len(piece) < 2 or NOT_AN_ACT.match(piece) or piece in out:
            continue
        out.append(piece)
    return out[:8]


def short_bill(acts, limit=70):
    if len(acts) <= limit:
        return acts
    cut = acts[:limit].rsplit(",", 1)[0]
    return (cut if len(cut) > 20 else acts[:limit].rstrip()) + " + more"


def start_iso(d, t):
    """ISO start for structured data; a set before 5 AM belongs to the next day."""
    m = minutes(t)
    if m is None:
        return d.isoformat()
    if m < 300:
        d = d + timedelta(days=1)
    dt = datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=NY)
    return dt.isoformat()


# ---------- page pieces ----------
HEAD = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <meta name="color-scheme" content="light dark" />
    <title>{title} | Show Me NYC</title>
    <meta name="description" content="{desc}" />
    <link rel="canonical" href="{url}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Show Me NYC" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc}" />
    <meta property="og:url" content="{url}" />
    <meta property="og:image" content="{site}og.png?v=3" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta name="twitter:card" content="summary_large_image" />
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%23111'/%3E%3Cpath fill='%23ff4d4d' d='M3 29V17h6v12zM10 29V11l6-3v21zM17 29V13h2V8h1V3h1v5h1v5h2v16zM25 29V19h4v10z'/%3E%3C/svg%3E" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;900&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="../pages.css" />{extra}
  </head>
"""

# A small page at an old address that sends people on to the new one. It
# carries the same preview text so links already shared still unfurl.
REDIRECT = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title} | Show Me NYC</title>
    <meta name="description" content="{desc}" />
    <meta name="robots" content="noindex" />
    <link rel="canonical" href="{site}shows/{new}.html" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Show Me NYC" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc}" />
    <meta property="og:url" content="{site}shows/{new}.html" />
    <meta property="og:image" content="{site}og.png?v=3" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta http-equiv="refresh" content="0; url={new}.html" />
    <script>location.replace("{new}.html" + location.hash);</script>
  </head>
  <body>
    <p><a href="{new}.html">This show's page has moved. Continue.</a></p>
  </body>
</html>
"""

TOP = """    <div class="wrap">
      <header class="top">
        <a class="brand" href="../">Show&nbsp;Me&nbsp;<span>NYC</span></a>
        <a class="back" href="{back}">{back_label}</a>
      </header>
"""


def footer(gunk_url, other_name, other_url):
    return f"""      <footer class="colophon">
        Sources: <a href="{esc(gunk_url)}" target="_blank" rel="noopener">GUNK New York</a>, <a href="{esc(other_url)}" target="_blank" rel="noopener">{esc(other_name)}</a> and venue calendars. Listings can change — check the venue before you head out.
      </footer>
    </div>
    <script src="../pages.js"></script>
  </body>
</html>
"""


def row_li(s, slug, d, with_date=True, with_venue=False):
    when = (f"{DOW[d.weekday()][:3]} {s[DAY]} · " if with_date else "") + (s[TIME] or "Time TBA")
    extra = f'<span class="v">{esc(s[VENUE])}</span>' if with_venue else ""
    age = f'<span class="badge">{esc(age_label(s[AGE]))}</span>' if s[AGE] else ""
    return (f'          <li data-date="{d.isoformat()}"><a href="../shows/{slug}.html">'
            f'<span class="t">{esc(when)}</span><span class="a">{esc(s[ACTS])}{extra}</span>{age}</a></li>\n')


def build():
    shows, geo, area, year, month, gunk_url, other_name, other_url = load()
    mon = MONTHS[month - 1]
    shows.sort(key=sort_key)

    slugs = unique_slugs(shows, year, month)
    astral = [s[ACTS] for s in shows if any(ord(c) > 0xFFFF for c in s[ACTS][:40])]
    if astral:
        print(f"WARNING: {len(astral)} bills start with emoji-range characters; saved-show keys may not match", file=sys.stderr)

    by_venue, by_day = {}, {}
    for s, sl in zip(shows, slugs):
        by_venue.setdefault(s[VENUE], []).append((s, sl))
        by_day.setdefault(s[DAY], []).append((s, sl))
    vslug = {}
    for v in by_venue:
        sl = venue_slug(v)
        if sl in vslug.values():
            sl += "-2"
        vslug[v] = sl

    (ROOT / "shows").mkdir(exist_ok=True)
    (ROOT / "venues").mkdir(exist_ok=True)
    # Clear only this month's show pages; earlier months are permanent.
    prefix = f"{year}-{month:02d}-"
    for old in (ROOT / "shows").glob(prefix + "*.html"):
        old.unlink()

    foot = footer(gunk_url, other_name, other_url)
    save_key = f"smn-saved-{year}-{month}"

    # ----- show pages -----
    written, redirects = set(), {}
    for s, sl in zip(shows, slugs):
        written.add(sl)
        d = date(year, month, s[DAY])
        ar = area.get(s[VENUE], "")
        when = f"{DOW[d.weekday()]} {mon[:3]} {s[DAY]}" + (f" · {s[TIME]}" if s[TIME] else "")
        when_short = f"{DOW[d.weekday()][:3]} {mon[:3]} {s[DAY]}" + (f", {s[TIME]}" if s[TIME] else "")
        title = f"{short_bill(s[ACTS])} at {s[VENUE]} — {when_short}"
        bits = [b for b in (age_label(s[AGE]), AREA_NAME.get(ar, ""), s[NOTE]) if b]
        desc = " · ".join(bits + ["Tickets, map and what else is on that night."])
        url = f"{SITE}shows/{sl}.html"
        sold = bool(re.search(r"sold-?out", s[URL], re.I))

        ld = {
            "@context": "https://schema.org", "@type": "MusicEvent",
            "name": s[ACTS], "startDate": start_iso(d, s[TIME]),
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            # No street addresses in the data, so "address" is left out rather than guessed.
            "location": {"@type": "Place", "name": s[VENUE]},
            "performer": [{"@type": "MusicGroup", "name": a} for a in act_names(s[ACTS])],
            "url": url,
        }
        if s[VENUE] in geo:
            ld["location"]["geo"] = {"@type": "GeoCoordinates", "latitude": geo[s[VENUE]][0], "longitude": geo[s[VENUE]][1]}
        if s[URL]:
            ld["offers"] = {"@type": "Offer", "url": s[URL],
                            "availability": "https://schema.org/" + ("SoldOut" if sold else "InStock")}
        extra = '\n    <script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"

        key = f"{s[DAY]}|{s[VENUE]}|{s[TIME]}|{s[ACTS][:40]}"
        m = minutes(s[TIME])
        cal_day = d + timedelta(days=1) if (m is not None and m < 300) else d
        cal_start = cal_day.strftime("%Y%m%d") + (f"T{m // 60:02d}{m % 60:02d}00" if m is not None else "")
        cal_desc = "\n".join([b for b in (age_label(s[AGE]), s[NOTE], ("Tickets: " + s[URL]) if s[URL] else "") if b]
                             + ["Listings can change — check the venue before you head out."])

        h = HEAD.format(title=esc(title), desc=esc(desc), url=url, site=SITE, extra=extra)
        h += (f'  <body data-kind="show" data-date="{d.isoformat()}" data-late="{1 if (m is not None and m < 300) else 0}" '
              f'data-save-key="{save_key}" data-show-key="{esc(key)}" data-cal-start="{cal_start}" '
              f'data-cal-title="{esc(s[ACTS] + " at " + s[VENUE])}" data-cal-venue="{esc(s[VENUE])}" '
              f'data-cal-desc="{esc(cal_desc)}" data-cal-file="{sl}.ics">\n')
        h += TOP.format(back=f"../#day-{s[DAY]}", back_label="← All shows")
        h += "      <main>\n"
        h += f'        <p class="when">{esc(when)}</p>\n        <h1>{esc(s[ACTS])}</h1>\n'
        where = f'<a class="venue" href="../venues/{vslug[s[VENUE]]}.html">{esc(s[VENUE])}</a>'
        if ar and ar != "out":
            where += f' <span class="area">{AREA_NAME[ar]}</span>'
        if s[VENUE] in geo and ar:
            where += f' <a class="map" href="{esc(map_url(s[VENUE], ar))}" target="_blank" rel="noopener">Map</a>'
        h += f'        <p class="where">{where}</p>\n'
        tags = []
        if s[AGE]:
            tags.append(f'<span class="badge">{esc(age_label(s[AGE]))}</span>')
        if ar == "out":
            tags.append('<span class="badge dotted">Out of town</span>')
        if s[SRC] == "club":
            tags.append('<span class="badge">Club night</span>')
        if s[NOTE]:
            tags.append(f'<span class="note">{esc(s[NOTE])}</span>')
        if tags:
            h += f'        <p class="tags">{" ".join(tags)}</p>\n'
        h += '        <p class="past-note" id="pastNote" hidden>This show has already happened.</p>\n'
        h += '        <div class="actions">\n'
        if s[URL]:
            h += (f'          <a class="btn primary{" sold" if sold else ""}" href="{esc(s[URL])}" target="_blank" rel="noopener">'
                  f'{"Sold out" if sold else "Tickets"}</a>\n')
        h += ('          <button class="btn" id="saveBtn" aria-pressed="false">☆ Save</button>\n'
              '          <button class="btn" id="calBtn">Add to calendar</button>\n'
              '          <button class="btn" id="shareBtn">Share</button>\n        </div>\n')
        if not s[URL]:
            h += '        <p class="hint">No ticket link listed. Check the venue for tickets or door price.</p>\n'

        names = act_names(s[ACTS])
        if names:
            h += '        <section>\n          <h2>Listen first</h2>\n          <ul class="listen">\n'
            for a in names:
                q = quote(a)
                h += (f'            <li><b>{esc(a)}</b><span>'
                      f'<a href="https://bandcamp.com/search?q={quote_plus(a)}" target="_blank" rel="noopener">Bandcamp</a>'
                      f'<a href="https://open.spotify.com/search/{q}" target="_blank" rel="noopener">Spotify</a>'
                      f'<a href="https://www.youtube.com/results?search_query={quote_plus(a)}" target="_blank" rel="noopener">YouTube</a>'
                      f'</span></li>\n')
            h += '          </ul>\n        </section>\n'

        later = [(o, osl) for o, osl in by_venue[s[VENUE]] if sort_key(o) > sort_key(s)][:5]
        if later:
            h += f'        <section>\n          <h2>Next at {esc(s[VENUE])}</h2>\n          <ul class="rows">\n'
            for o, osl in later:
                h += row_li(o, osl, date(year, month, o[DAY])).replace("          <li", "            <li")
            h += f'          </ul>\n          <a class="more" href="../venues/{vslug[s[VENUE]]}.html">All shows at {esc(s[VENUE])} →</a>\n        </section>\n'
        else:
            h += (f'        <section>\n          <a class="more" href="../venues/{vslug[s[VENUE]]}.html">'
                  f'All shows at {esc(s[VENUE])} →</a>\n        </section>\n')

        if ar and ar != "out":
            near = [(o, osl) for o, osl in by_day[s[DAY]] if o is not s and area.get(o[VENUE]) == ar][:6]
            if near:
                h += f'        <section>\n          <h2>Also that night in {AREA_NAME[ar]}</h2>\n          <ul class="rows">\n'
                for o, osl in near:
                    h += row_li(o, osl, d, with_date=False, with_venue=True).replace("          <li", "            <li")
                h += '          </ul>\n        </section>\n'
        mc_q = f"show={sl}&venue={quote(s[VENUE])}&night={d.isoformat()}"
        h += (f'        <a class="mc-link" id="mcLink" href="../missed-connections.html?{esc(mc_q)}" hidden>'
              'Were you there? Read or leave a missed connection →</a>\n')
        h += "      </main>\n" + foot
        (ROOT / "shows" / f"{sl}.html").write_text(h, encoding="utf8")
        if (year, month) in LEGACY_MONTHS:
            # First row wins if two rows shared an old address, as it did then.
            redirects.setdefault(legacy_slug(s, month), (sl, title, desc))

    # ----- redirect pages for addresses shared under the first scheme -----
    for old, (new, title, desc) in redirects.items():
        (ROOT / "shows" / f"{old}.html").write_text(REDIRECT.format(
            title=esc(title), desc=esc(desc), site=SITE, new=new), encoding="utf8")

    # ----- venue pages -----
    for v, items in by_venue.items():
        ar = area.get(v, "")
        n = len(items)
        title = f"{v} — shows in {mon} {year}"
        desc = f"{n} show{'s' if n != 1 else ''} at {v} in {mon} {year}" + (f" · {AREA_NAME[ar]}" if ar else "") + ". Times, tickets and what's on each night."
        url = f"{SITE}venues/{vslug[v]}.html"
        h = HEAD.format(title=esc(title), desc=esc(desc), url=url, site=SITE, extra="")
        h += '  <body data-kind="venue">\n' + TOP.format(back="../", back_label="← All shows") + "      <main>\n"
        if ar:
            h += f'        <p class="when">{AREA_NAME[ar]}</p>\n'
        h += f"        <h1>{esc(v)}</h1>\n"
        where = f'<span id="venueCount">{n} show{"s" if n != 1 else ""} in {mon}</span>'
        if v in geo and ar:
            where = f'<a class="map" href="{esc(map_url(v, ar))}" target="_blank" rel="noopener">Map</a> ' + where
        h += f'        <p class="where">{where}</p>\n'
        h += '        <section>\n          <h2 id="venueHead">Shows</h2>\n          <ul class="rows" id="venueRows">\n'
        for o, osl in items:
            h += row_li(o, osl, date(year, month, o[DAY])).replace("          <li", "            <li")
        h += '          </ul>\n          <button class="more as-btn" id="earlierBtn" hidden></button>\n        </section>\n'
        h += "      </main>\n" + foot
        (ROOT / "venues" / f"{vslug[v]}.html").write_text(h, encoding="utf8")

    # ----- sitemap -----
    all_shows = sorted(f.stem for f in (ROOT / "shows").glob("*.html") if re.match(r"\d{4}-\d{2}-\d{2}-", f.name))
    all_venues = sorted(f.stem for f in (ROOT / "venues").glob("*.html"))
    urls = [SITE, SITE + "missed-connections.html"] + [f"{SITE}venues/{s}.html" for s in all_venues] + [f"{SITE}shows/{s}.html" for s in all_shows]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{esc(u)}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf8")

    print(f"pages: {len(written)} shows this month ({len(all_shows)} in all), {len(vslug)} venues, {len(redirects)} redirects")
    return written, vslug


def main():
    build()


if __name__ == "__main__":
    sys.exit(main())
