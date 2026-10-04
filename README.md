# Show Me NYC

Every NYC show for the month in one list: DIY/indie listings from GUNK New York plus Oh My Rockness.
Live at https://talmanjoseph-creator.github.io/gunk-shows-dashboard/

## Files

- `index.html` — the page (markup, styles, script). Nothing month-specific lives here.
- `shows-data.js` — one month of listings: issue details, shows, venue coordinates, venue areas.
- `tools/clean_shows.py` — cleans `shows-data.js` in place.
- `og.png` — the preview image used when the link is shared.

## Updating for a new month

1. In `shows-data.js`, update `SHOW_META` (year, month, issue details, notes) and replace the rows in `SHOWS`.
2. Add coordinates to `GEO` for any venue that is new.
3. Run `python3 tools/clean_shows.py`. It merges venue spellings, removes duplicate listings,
   sorts each day by start time, and regenerates `AREA`. It prints what it merged and which
   venues have no coordinates, so check that output.
4. If it puts a venue in the wrong area, add it to `AREA_OVERRIDES` in the script and run it again.
   New venue spellings go in `VENUE_ALIASES`.

## Shareable links

Filters are kept in the URL, so a filtered view can be shared as is, e.g.
`?area=bush&open=AA` (all-ages shows in Bushwick / Ridgewood) or `?src=gunk#day-17`.
