---
name: pre-push-check
description: Run the AGENTS.md "check before pushing" on index.html — phone and desktop width, lands on today, day heading below the sticky bar, no console errors, every show link points at a real page in shows/. Use before pushing or opening a pull request that touches index.html, shows-data.js, pages.css/pages.js, or the tools.
---

# Pre-push check

Run from the repo root:

```bash
node .claude/skills/pre-push-check/check.cjs
```

If today falls outside the listings window (the script warns about a stale note), rerun with a date inside it:

```bash
node .claude/skills/pre-push-check/check.cjs --date 2026-11-07
```

What it checks, at 390px (phone) and 1280px (desktop):

1. No JavaScript errors or console errors from the site's own code. Failures reaching outside hosts (Supabase, map tiles) are only warnings: the list has to load without them.
2. The page lands on today: the `section.day.tonight` heading is near the top of the screen.
3. That heading sits below the sticky bar (`.controls`), not under it.
4. Every `shows/...` link the page renders exists on disk. A miss means `show_slug()` in `tools/build_pages.py` and `showSlug()` in `index.html` no longer match, or the pages were not rebuilt after a data change.

It saves screenshots to the system temp folder (`pre-push-phone.png`, `pre-push-desktop.png`). Look at them if anything fails.

Exit code 0 means pass. On a failure, fix it before pushing. Do not change the checks to make them pass. Report what failed in the pull request if you cannot fix it.
