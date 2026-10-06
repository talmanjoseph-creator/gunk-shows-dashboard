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

## Missed connections

Posts and replies are stored in the owner's Supabase project, not in this repo.

- `missed-connections.html` has the post box and the list. Visitors give a name and a message, no login. Replies work the same way, one level deep.
- **Nothing shows until it is approved.** New posts and replies are saved as not approved, and the public can only read approved rows.
- `mc-admin.html` is the owner's page. Sign in with email and password, then Approve, Take down or Delete. The password is set on that page ("Set or change your password") after signing in once with the emailed link, which is also the way back in if the password is forgotten. The sign-in is kept on that device and renewed automatically until Sign out is tapped. Only emails listed in the `connection_admins` table can approve anything, whoever signs in.
- `supabase/setup.sql` creates the table and every rule above. It was tested in Postgres and is safe to run again. The admin email is added in Supabase directly and is never saved here.
- `connections-data.js` holds the project URL and the public anon key. That key is meant to be public; it can only do what `setup.sql` allows. **Never commit the service_role key or a database password.**
- Posts older than `expiresDays` are hidden by the page.
- Show pages link to `missed-connections.html?show=<slug>&venue=…&night=…` from the night of the show onward, so a post made from there is tied to that show.
- If `supabaseUrl` or `supabaseKey` is empty, the page falls back to the older Google Form link.

## Shows sent in by bands

- `submit.html` is the form: acts, venue, night, time, ages, ticket link, a note and an optional contact email. No login.
- Sent-in shows are stored in the owner's Supabase project, table `submitted_shows`. `supabase/submitted-shows.sql` creates it and its rules; run it after `setup.sql`. It was tested in Postgres and is safe to run again.
- **Nothing shows until it is approved.** `mc-admin.html` lists the shows waiting, flags one that looks like it is already on the list, and shows the contact email to the owner only.
- Approved shows appear on the main list right away (read from Supabase when the page loads). If Supabase can't be reached the list loads without them.
- Each approved show has a page at once: `show.html?id=<number>`. It has the details, tickets, a calendar button and a share kit: a 4:5 poster drawn in the browser, words to copy and the link. Its link preview is the site's general one, because the page is filled in by script; the generated page in `shows/` (after the next data update) has a preview of its own.
- On `mc-admin.html`, an approved show has "Open its page" and, if the band left an email, "Email the band their link", which opens a ready-written email in the owner's own mail app. Nothing is sent automatically.
- `python3 tools/pull_submissions.py` copies approved shows into `shows-data.js` (source `sub`) and runs the cleanup, which gives them a show page, a venue page and a calendar button. Add `--dry-run` to see what it would add. Run it as part of each data update.
- The contact email can't be read through the public API by anyone; the owner's page gets it through `submitted_show_contacts()`.

## Shareable links

Filters are kept in the URL, so a filtered view can be shared as is, e.g.
`?area=bush&open=AA` (all-ages shows in Bushwick / Ridgewood), `?src=gunk#day-17`,
or `?club=1` (club nights only). Club nights are in the list until `CLUB_BY_DEFAULT`
in `index.html` is set to false, which hides them unless that chip is on.
