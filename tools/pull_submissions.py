#!/usr/bin/env python3
"""Fold approved sent-in shows into shows-data.js.

Bands add shows on submit.html; the owner approves them on mc-admin.html.
Approved shows already appear on the main list (index.html reads them from
Supabase), but they only get their own show page, venue page and calendar
button once they are rows in shows-data.js. This script copies them over.

  python3 tools/pull_submissions.py            # add them, then run clean_shows.py
  python3 tools/pull_submissions.py --dry-run  # only print what would be added

It reads with the public key from connections-data.js, so it can only see
approved rows and never sees a contact email. It does not change anything in
the database. Rows are added with source "sub". A show that is already in the
list (same day, venue and first act) is skipped.
"""
import json
import re
import sys
import urllib.request
from calendar import monthrange
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "shows-data.js"
SETTINGS = ROOT / "connections-data.js"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean_shows  # noqa: E402

TIME_RE = re.compile(r"^(1[0-2]|[1-9]):[0-5][0-9] (AM|PM)$")
URL_RE = re.compile(r'^https://[a-z0-9-]+(\.[a-z0-9-]+)+(/[^\s"<>]*)?$', re.I)
AGES = {"AA", "16", "18", "21"}


def key(day, venue, acts):
    def norm(t):
        return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    return (day, norm(clean_shows.canon_venue(venue)), norm(acts.split(",")[0]))


def fetch(base, api_key, year, month):
    last = monthrange(year, month)[1]
    query = (
        "select=id,night,start_time,venue,acts,note,age,ticket_url"
        f"&approved=is.true&night=gte.{year}-{month:02d}-01&night=lte.{year}-{month:02d}-{last:02d}"
        "&order=night.asc,id.asc&limit=1000"
    )
    req = urllib.request.Request(
        f"{base.rstrip('/')}/rest/v1/submitted_shows?{query}",
        headers={"apikey": api_key, "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def to_row(r):
    """A database row as a shows-data.js row, or None if it is not usable."""
    try:
        day = int(str(r["night"])[8:10])
    except (KeyError, ValueError):
        return None
    venue = clean_shows.canon_venue(" ".join(str(r.get("venue") or "").split()))
    acts = " ".join(str(r.get("acts") or "").split())
    if not venue or not acts:
        return None
    time = r.get("start_time") or ""
    age = r.get("age") or ""
    url = clean_shows.direct_url(r.get("ticket_url") or "")
    return [
        day,
        time if TIME_RE.match(time) else "",
        venue,
        acts,
        " ".join(str(r.get("note") or "").split())[:140],
        age if age in AGES else "",
        "sub",
        url if URL_RE.match(url) else "",
    ]


def main():
    dry = "--dry-run" in sys.argv[1:]
    settings = SETTINGS.read_text(encoding="utf8")
    base = re.search(r'supabaseUrl:\s*"([^"]*)"', settings).group(1)
    api_key = re.search(r'supabaseKey:\s*"([^"]*)"', settings).group(1)
    if not base or not api_key:
        print("Supabase is not set in connections-data.js; nothing to pull.")
        return 0
    src = DATA.read_text(encoding="utf8")
    year = int(re.search(r"\byear:\s*(\d+)", src).group(1))
    month = int(re.search(r"\bmonth:\s*(\d+)", src).group(1))
    start = src.index("var SHOWS = [") + len("var SHOWS = ")
    end = src.index("\n];", start) + 2
    shows = json.loads(re.sub(r",\s*\]$", "]", src[start:end].strip()))
    have = {key(s[0], s[2], s[3]) for s in shows}

    added = []
    try:
        found = fetch(base, api_key, year, month)
    except OSError as e:  # includes HTTP and network errors
        print(f"Couldn't read the sent-in shows ({e}). Nothing changed.")
        return 1
    for r in found:
        row = to_row(r)
        if row is None:
            print(f"  skipped #{r.get('id')}: not usable")
            continue
        k = key(row[0], row[2], row[3])
        if k in have:
            continue
        have.add(k)
        added.append(row)
        print(f"  + {month}/{row[0]} {row[1] or 'no time'} · {row[2]} · {row[3][:60]}")
    if not added:
        print("No new approved shows to add.")
        return 0
    if dry:
        print(f"{len(added)} would be added (dry run, nothing written).")
        return 0
    rows = ",\n".join("  " + json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in shows + added)
    DATA.write_text(src[:start] + "[\n" + rows + "\n]" + src[end:], encoding="utf8")
    print(f"{len(added)} added. Cleaning and rebuilding pages…")
    return clean_shows.main()


if __name__ == "__main__":
    sys.exit(main())
