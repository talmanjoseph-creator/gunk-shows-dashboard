# Show Me NYC

Every NYC show for the month in one list: DIY/indie listings from GUNK New York and around the city.
Live at https://talmanjoseph-creator.github.io/gunk-shows-dashboard/

## Files

- `index.html` — the page (markup, styles, script). Nothing month-specific lives here.
- `shows-data.js` — one month of listings: issue details, shows, venue coordinates, venue areas.
- `tools/clean_shows.py` — cleans `shows-data.js` in place.
- `tools/fetch_venues.py` — pulls club nights from venues' own public calendars.
- `og.png` — the preview image used when the link is shared.

## Updating for a new month

1. In `shows-data.js`, update `SHOW_META` (year, month, source details) and replace the rows in `SHOWS`.
2. Pull club nights from the venues' own calendars:
   `python3 tools/fetch_venues.py --merge`
   It reads the year and month from `SHOW_META`. Add `--from-day 4` to start partway
   through the month. It prints which venues it read and which it skipped.
   New venues it knows about are added to `GEO`.
3. Add coordinates to `GEO` for any venue that is still new.
4. Run `python3 tools/clean_shows.py`. It merges venue spellings, removes duplicate listings,
   sorts each day by start time, regenerates `AREA`, and replaces affiliate-redirect ticket links
   with the direct ticket page. It prints what it merged and which
   venues have no coordinates, so check that output.
5. If it puts a venue in the wrong area, add it to `AREA_OVERRIDES` in the script and run it again.
   New venue spellings go in `VENUE_ALIASES`.

## Show and venue pages

Every show has its own page in `shows/` and every venue in `venues/`. They are generated files: do not edit them by hand.

- `tools/build_pages.py` writes them (plus `sitemap.xml`) from `shows-data.js`. `tools/clean_shows.py` runs it for you at the end, so one command keeps data and pages in step.
- `pages.css` and `pages.js` are the shared styles and behavior for those pages. `404.html` is shown for a show link that no longer exists.
- The main list links each show to `shows/<slug>.html`. The slug starts with the full date (`2026-10-09-babys-all-right-cardinal-bloom-630pm`) and is computed twice: `show_slug()` and `unique_slugs()` in `tools/build_pages.py`, and `showSlug()` plus the slug loop in `index.html`. Two rows that would share a name get `-2`, `-3` in list order. Change one side and you must change the other.
- **Show links are permanent.** The generator only rebuilds the pages for the month in `shows-data.js`; pages from earlier months stay where they are so shared links keep working.
- The October 2026 pages were first published without the year (`oct-09-...`). Those addresses are small redirect pages now; leave them in place.

## Shareable links

Filters are kept in the URL, so a filtered view can be shared as is, e.g.
`?area=bush&open=AA` (all-ages shows in Bushwick / Ridgewood), `?src=gunk#day-17`,
or `?club=1` (club nights only). Club nights are in the list until `CLUB_BY_DEFAULT`
in `index.html` is set to false, which hides them unless that chip is on.
