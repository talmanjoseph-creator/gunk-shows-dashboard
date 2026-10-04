# Notes for anyone (or any agent) changing this site

More than one person and more than one AI agent push to this repo. Read this before editing.

## Before you change anything

1. **Pull the latest `main` first.** Do not work from an older copy of `index.html`. The page was restructured on Oct 4, 2026; an older copy is a different file and pushing it would undo that work.
2. **Never force-push `main`, and never replace a whole file from a stale copy.** Make the smallest edit that does the job.
3. Work on a branch and merge with a pull request.

## How the site is laid out

- `index.html` — markup, styles and script. It contains **no listings and nothing month-specific**.
- `shows-data.js` — all listings data: `SHOW_META`, `SHOWS`, `GEO`, `AREA`. Listings go here, not in `index.html`.
- `tools/clean_shows.py` — run it after changing `shows-data.js`. It merges venue spellings, removes duplicates, sorts by start time, regenerates `AREA`, and unwraps affiliate ticket links.
- `shows/` and `venues/` — one generated page per show and per venue. **Never edit these by hand**; `tools/build_pages.py` rewrites both folders from `shows-data.js`, and `tools/clean_shows.py` runs it automatically. If you change the data, the pages must be regenerated in the same pull request.
- `pages.css`, `pages.js`, `404.html` — shared styles, behavior and not-found page for the generated pages.
- The show page name is computed in two places that must match: `show_slug()` in `tools/build_pages.py` and `showSlug()` in `index.html`.
- `og.png` — share preview image.
- `README.md` — how to update for a new month.

## How things stand (check with the owner before undoing any of these)

- **Sources are credited in the footer only.** The footer's Sources line names and links GUNK New York and Oh My Rockness. The masthead and the filters do not name Oh My Rockness.
- **Ticket links are direct**, never affiliate redirects (`evyy.net`, `pxf.io`). The cleanup script enforces this.
- **Resident Advisor is not a source.** Their terms of use forbid automated collection without written permission, so do not scrape it.
- **Copy is short.** Masthead: tagline, the "shows tonight" button, one line of totals. No stats grid, no source paragraph.
- **Rows show no source badge and there is no source filter.** GUNK is credited in the footer only. In the data, `gunk`, `other`, `club` and `both` still record where a row came from; `both` means GUNK plus another source.
- **Out-of-town shows are hidden by default** and tagged when shown.
- **The street-level home location must not appear** anywhere in the code or comments.

## Missed connections

- `missed-connections.html` shows posts from `connections-data.js`. **Do not add, edit or remove a post unless the owner has approved that exact post.** Do not write posts yourself, not even as samples.
- A post must never contain last names, social handles, phone numbers, emails, or anything else that identifies a person.
- Submissions and people's contact details live in the owner's private spreadsheet. Never copy them into this repo, a commit message or a pull request.

## Check before pushing

Open `index.html` in a browser at phone width and desktop width. The page should land on today, the day heading should sit below the sticky bar, and the browser console should show no errors.
