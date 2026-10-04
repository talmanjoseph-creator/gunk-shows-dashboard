#!/usr/bin/env python3
"""Clean the listings in shows-data.js.

Run after pasting in new listings:  python3 tools/clean_shows.py

  1. Normalizes venue names (trims whitespace, merges known aliases).
  2. Merges duplicate listings (same day + venue with a matching bill).
     "both" means GUNK plus another source, and keeps the GUNK wording.
     A club night merged with an "other" row stays "club".
  3. Sorts each day by start time (after-midnight sets go last).
  4. Regenerates AREA (venue -> area) from the GEO coordinates.
  5. Replaces affiliate-redirect ticket links with the direct ticket page.

Add new spellings to VENUE_ALIASES as they turn up, and fix a wrong area
in AREA_OVERRIDES.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

INDEX = Path(__file__).resolve().parent.parent / "shows-data.js"

# alias -> canonical name
VENUE_ALIASES = {
    "ALPHAVILLE": "Alphaville",
    "TV EYE": "TV Eye",
    "Le Poisson Rouge": "(Le) Poisson Rouge",
    "Trans Pecos": "Trans-Pecos",
    "Bric House": "BRIC House",
    "Jalopy Theater": "Jalopy Theatre",
    "Gutter Bar": "The Gutter",
    "Rough Trade": "Rough Trade NYC",
    "Footlight Underground at The Windjammer": "Windjammer",
}
# Note to add when an alias carried information the canonical name drops.
ALIAS_NOTES = {"Footlight Underground at The Windjammer": "Footlight Underground presents"}

DAY, TIME, VENUE, ACTS, NOTE, AGE, SRC, URL = range(8)

# Area codes used by the page's Area filter (labels live in index.html).
#   bush = Bushwick / Ridgewood      wbg = Williamsburg / Greenpoint
#   bk   = Rest of Brooklyn          qns = Queens
#   les  = Manhattan below 14th St   mid = Manhattan above 14th St
#   bx   = The Bronx / Staten Island out = outside the five boroughs
AREA_OVERRIDES = {
    "Under the K Bridge Park": "wbg",
    "UBS Arena": "out",  # Elmont, just over the Nassau line
    "Sleepwalk": "bush",  # Bushwick Ave, a block inside the Williamsburg box
    "Venue TBA": "",  # placeholder coordinates, not a real location
}


def area_for(lat, lng):
    """Rough area from coordinates. Good enough for a filter; override misses."""
    # Outside the five boroughs: Westchester and north, Long Island, New Jersey.
    if lat > 40.917 or lat < 40.49 or lng > -73.70:
        return "out"
    if lng < -74.03 and not (lat < 40.65 and lng > -74.26):  # NJ, but not Staten Island
        return "out"
    if lat < 40.65 and lng < -74.05:
        return "bx"  # Staten Island
    # East River, as longitude by latitude (Manhattan is west of this line).
    river = [(40.700, -73.997), (40.710, -73.975), (40.720, -73.968), (40.730, -73.966),
             (40.740, -73.963), (40.750, -73.960), (40.760, -73.950), (40.780, -73.938),
             (40.800, -73.928), (40.835, -73.934), (40.880, -73.910)]
    if lat >= 40.700:
        for (la0, lo0), (la1, lo1) in zip(river, river[1:]):
            if la0 <= lat <= la1:
                edge = lo0 + (lo1 - lo0) * (lat - la0) / (la1 - la0)
                break
        else:
            edge = river[-1][1]
        if lng < edge:
            # 14th St runs at a slant; this is its latitude at a given longitude.
            fourteenth = 40.7347 - 0.444 * (lng + 73.9907)
            return "les" if lat < fourteenth else "mid"
        if lat > 40.800:
            return "bx"
    if 40.680 <= lat <= 40.720 and -73.937 <= lng <= -73.885:
        return "bush"
    if 40.700 <= lat <= 40.740 and -73.972 <= lng < -73.937:
        return "wbg"
    if lat > 40.735 or lng > -73.885:
        return "qns"
    return "bk"


# Affiliate redirectors that wrap the real ticket page in a "u" parameter.
REDIRECT_HOSTS = ("evyy.net", "pxf.io", "sjv.io")
# Tracking parameters to drop from the unwrapped link.
TRACKING_PARAMS = {"aff", "subid1", "subid2", "subid3", "irclickid", "irgwc", "clickid"}


def direct_url(url):
    """Unwrap an affiliate redirect to the ticket page it points at."""
    if not url:
        return url
    # Dice marketing links (.../partner/tickets/event/<slug>?utm=...) are the
    # same event page as https://dice.fm/event/<slug>.
    dice = re.search(r"https?://(?:www\.)?dice\.fm/(?:partner/tickets/)?event/([^?#\s]+)", url, re.I)
    if dice:
        return "https://dice.fm/event/" + dice.group(1).strip("/")
    parts = urlsplit(url)
    if not parts.netloc.endswith(REDIRECT_HOSTS):
        return url
    # The target may be percent-encoded or pasted raw (with its own "?").
    m = re.search(r"[?&]u=(.+)$", url)
    if not m:
        return url
    target = m[1]
    if not target.lower().startswith("http"):
        return url
    if "%3A%2F%2F" in target[:16].upper():
        target = unquote(target.split("&")[0])
    t = urlsplit(target)
    if not t.netloc:
        return url
    query = [(k, v) for k, v in parse_qsl(t.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    return urlunsplit((t.scheme, t.netloc, t.path, urlencode(query), t.fragment))


def canon_venue(name):
    name = name.strip()
    return VENUE_ALIASES.get(name, name)


def minutes(t):
    m = re.match(r"(\d+):(\d+)\s*(AM|PM)", t or "", re.I)
    if not m:
        return 99999  # no time listed: end of the day
    h = int(m[1]) % 12 + (12 if m[3].upper() == "PM" else 0)
    mins = h * 60 + int(m[2])
    return mins + 1440 if mins < 300 else mins  # before 5 AM = late night


def act_set(acts):
    out = set()
    for a in re.split(r"[,:/]", acts):
        a = re.sub(r"\(.*?\)", "", a)
        a = re.sub(r"[^a-z0-9]", "", a.lower())
        if len(a) > 2:
            out.add(a)
    return out


def similar(a, b):
    """Act names equal, or within one edit of each other (typos)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1 or min(len(a), len(b)) < 5:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:] or a[i + 1:] == b[i + 1:] or (
        len(a) == len(b) and a[i + 1:i + 2] == b[i:i + 1] and a[i:i + 1] == b[i + 1:i + 2] and a[i + 2:] == b[i + 2:])


def overlap(x, y):
    a, b = act_set(x[ACTS]), act_set(y[ACTS])
    if not a or not b:
        return 0.0
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    hits = sum(1 for s in small if any(similar(s, t) for t in big))
    return hits / len(small)


def is_dupe(x, y):
    if x[DAY] != y[DAY] or x[VENUE] != y[VENUE]:
        return False
    # One ticket page is one night, even when the bills are worded differently.
    # A shared venue homepage used on several days is not this case.
    if x[URL] and x[URL] == y[URL]:
        return True
    ov = overlap(x, y)
    if x[TIME] == y[TIME]:
        return ov > 0
    # Different times: the same source means an early and a late set.
    # Across sources it is usually doors vs. show time, if the bills match.
    return x[SRC] != y[SRC] and ov > 0.5


def merged_source(a, b):
    """'both' is only GUNK plus something else. Club merged with other stays club."""
    srcs = {a, b}
    if "gunk" in srcs or "both" in srcs:
        return "gunk" if srcs <= {"gunk"} else "both"
    if "club" in srcs:
        return "club"
    return a if a == b else "other"


def url_rank(url):
    """Prefer a direct ticket page over an empty link or a redirect short link."""
    if not url:
        return 0
    host = urlsplit(url).netloc.lower()
    if host.endswith("ra.co") or "link.dice.fm" in host:
        return 1
    return 2


def merge(x, y):
    """Fold y into x. GUNK wording wins; the other row supplies what that one lacks."""
    src = merged_source(x[SRC], y[SRC])
    def gunkish(row):
        return row[SRC] in ("gunk", "both")
    if gunkish(x) and not gunkish(y):
        keep, other = x, y
    elif gunkish(y) and not gunkish(x):
        keep, other = y, x
    else:
        keep, other = (x, y) if len(act_set(x[ACTS])) >= len(act_set(y[ACTS])) else (y, x)
    out = list(keep)
    for f in (TIME, NOTE, AGE, URL):
        if not out[f]:
            out[f] = other[f]
    if url_rank(other[URL]) > url_rank(out[URL]):
        out[URL] = other[URL]
    out[SRC] = src
    return out


def clean(shows):
    for s in shows:
        raw = s[VENUE].strip()
        s[VENUE] = canon_venue(raw)
        # Drop the zine's trailing "*" headliner marks ("Mars Motel*"). An
        # asterisk inside a name ("Sub*T") is part of the name and stays.
        s[ACTS] = re.sub(r"\*(?=\s*(?:,|$))", "", s[ACTS]).strip()
        s[URL] = direct_url(s[URL])
        if raw in ALIAS_NOTES and not s[NOTE]:
            s[NOTE] = ALIAS_NOTES[raw]
    out, merged = [], []
    for s in shows:
        for i, o in enumerate(out):
            if is_dupe(o, s):
                out[i] = merge(o, s)
                merged.append((o, s))
                break
        else:
            out.append(list(s))
    out.sort(key=lambda s: (s[DAY], minutes(s[TIME])))
    return out, merged


def main():
    src = INDEX.read_text(encoding="utf8")
    start = src.index("var SHOWS = [") + len("var SHOWS = ")
    end = src.index("];", start) + 1
    shows = json.loads(re.sub(r",\s*\]$", "]", src[start:end].strip()))
    cleaned, merged = clean(shows)
    rows = ",\n".join("  " + json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in cleaned)
    src = src[:start] + "[\n" + rows + "\n]" + src[end:]

    # GEO: move coordinates from alias keys onto canonical names.
    g0 = src.index("var GEO = {")
    g1 = src.index("};", g0)
    lines, seen = [], set()
    entries = re.findall(r'^\s*("(?:[^"\\]|\\.)*"):\s*(\[[^\]]*\])', src[g0:g1], re.M)
    for key, coords in sorted(entries, key=lambda e: (canon_venue(json.loads(e[0])) != json.loads(e[0]))):
        name = canon_venue(json.loads(key))
        if name in seen:
            continue
        seen.add(name)
        lines.append((name, coords))
    lines.sort(key=lambda e: e[0].lower())
    body = ",\n".join("  " + json.dumps(n, ensure_ascii=False) + ": " + c for n, c in lines)
    src = src[:g0] + "var GEO = {\n" + body + "\n" + src[g1:]

    # AREA: venue -> area code, from coordinates plus overrides.
    areas = {}
    for name, coords in lines:
        lat, lng = json.loads(coords)
        areas[name] = AREA_OVERRIDES[name] if name in AREA_OVERRIDES else area_for(lat, lng)
    a0 = src.index("var AREA = {")
    a1 = src.index("};", a0)
    abody = ",\n".join("  " + json.dumps(n, ensure_ascii=False) + ": " + json.dumps(areas[n]) for n, _ in lines)
    src = src[:a0] + "var AREA = {\n" + abody + "\n" + src[a1:]

    INDEX.write_text(src, encoding="utf8")
    wrapped = sum(1 for s in cleaned if urlsplit(s[URL]).netloc.endswith(REDIRECT_HOSTS))
    print(f"{len(shows)} rows in, {len(cleaned)} out, {len(merged)} merged, {wrapped} affiliate links left")
    for a, b in merged:
        print(f"  Oct {a[DAY]:>2} {a[VENUE]}: [{a[SRC]} {a[TIME]}] {a[ACTS][:45]!r} + [{b[SRC]} {b[TIME]}] {b[ACTS][:45]!r}")
    venues = {s[VENUE] for s in cleaned}
    missing = sorted(venues - seen)
    if missing:
        print("No coordinates (no area, excluded from Close to home):", ", ".join(missing))
    by_area = {}
    for s in cleaned:
        by_area.setdefault(areas.get(s[VENUE]) or "-", set()).add(s[VENUE])
    for code in sorted(by_area):
        print(f"  {code:>4}: {', '.join(sorted(by_area[code]))}")


if __name__ == "__main__":
    sys.exit(main())
