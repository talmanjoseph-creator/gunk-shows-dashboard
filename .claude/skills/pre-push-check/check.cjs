#!/usr/bin/env node
/* Pre-push check for index.html (AGENTS.md "Check before pushing").
 *
 *   node .claude/skills/pre-push-check/check.cjs [--date YYYY-MM-DD]
 *
 * Serves the repo locally, opens index.html at phone and desktop width and checks:
 *   1. no JavaScript errors / console errors from the site's own code
 *   2. the page lands on today (the "tonight" day section is in view)
 *   3. that day's heading sits below the sticky bar, not under it
 *   4. every show link the page renders points at a page that exists in shows/
 *      (catches show_slug() in build_pages.py and showSlug() in index.html drifting)
 * Errors from outside hosts (e.g. Supabase unreachable) are reported as warnings:
 * the list must still load without them.
 * --date fakes "today" (useful when the real date is outside the listings window).
 * Exit code 0 = pass, 1 = fail.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
let chromium;
try { ({ chromium } = require("playwright")); }
catch (e) { console.error("Playwright is not available: " + e.message); process.exit(1); }

const ROOT = path.resolve(__dirname, "..", "..", "..");
const dateArg = (() => { const i = process.argv.indexOf("--date"); return i > 0 ? process.argv[i + 1] : ""; })();
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
  ".json": "application/json", ".xml": "application/xml", ".txt": "text/plain", ".svg": "image/svg+xml" };

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (p.endsWith("/")) p += "index.html";
  const file = path.join(ROOT, p);
  if (!file.startsWith(ROOT + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404); return res.end("not found");
  }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});

const VIEWPORTS = [
  { name: "phone", width: 390, height: 844, isMobile: true, hasTouch: true },
  { name: "desktop", width: 1280, height: 800 },
];

async function checkViewport(browser, base, vp) {
  const fails = [], warns = [];
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height },
    isMobile: !!vp.isMobile, hasTouch: !!vp.hasTouch,
    // Skip the title card (the site already skips it for reduced motion) so the
    // screenshot shows the list. The list loads underneath the card either way.
    reducedMotion: "reduce" });
  const page = await ctx.newPage();
  if (dateArg) {
    const t = new Date(dateArg + "T19:00:00").getTime();
    await page.addInitScript(`{ const T=${t}, D=Date; class F extends D { constructor(...a){ super(...(a.length?a:[T])); } static now(){ return T; } } window.Date = F; }`);
  }
  const local = (u) => !u || u.startsWith(base);
  page.on("pageerror", (e) => fails.push("JS error: " + e.message));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const u = (m.location() || {}).url || "";
    (local(u) && !/https?:\/\/(?!127\.0\.0\.1)/.test(m.text()) ? fails : warns).push("console: " + m.text().slice(0, 200));
  });
  page.on("requestfailed", (r) => { if (!local(r.url())) warns.push("request failed (outside host): " + r.url().slice(0, 100)); });

  await page.goto(base + "/index.html", { waitUntil: "load" });
  await page.waitForTimeout(1500); // let the landing scroll and any Supabase fetch settle

  const info = await page.evaluate(() => {
    const bar = document.querySelector(".controls");
    const sec = document.querySelector("section.day.tonight");
    const head = sec && (sec.querySelector(".day-head") || sec);
    const stale = document.getElementById("staleNote");
    const links = [...document.querySelectorAll('#days a[href^="shows/"]')].map((a) => a.getAttribute("href").split(/[?#]/)[0]);
    return {
      barBottom: bar ? bar.getBoundingClientRect().bottom : null,
      today: sec ? sec.id : null,
      todayHidden: sec ? sec.hidden || sec.offsetParent === null : null,
      headTop: head ? head.getBoundingClientRect().top : null,
      vh: window.innerHeight,
      stale: !!(stale && !stale.hidden),
      links,
    };
  });

  if (info.barBottom === null) fails.push("sticky bar (.controls) not found");
  if (!info.today) {
    (info.stale ? warns : fails).push(info.stale
      ? "today is outside the listings window (stale note shown); rerun with --date YYYY-MM-DD inside the window"
      : "no day section marked as tonight; the page did not land on today");
  } else if (info.todayHidden) {
    warns.push(`${info.today} is hidden by the default filters, so there is nothing to land on`);
  } else {
    if (info.headTop < info.barBottom - 1) fails.push(`day heading (${info.today}) is under the sticky bar: heading top ${info.headTop.toFixed(0)}px, bar bottom ${info.barBottom.toFixed(0)}px`);
    if (info.headTop > info.vh * 0.6) fails.push(`page did not scroll to today: ${info.today} heading is at ${info.headTop.toFixed(0)}px of ${info.vh}px`);
  }
  const missing = [...new Set(info.links)].filter((h) => !fs.existsSync(path.join(ROOT, h)));
  if (missing.length) fails.push(`${missing.length} show link(s) point at pages that do not exist (slug drift or pages not rebuilt), e.g. ${missing.slice(0, 3).join(", ")}`);

  await page.screenshot({ path: path.join(require("os").tmpdir(), `pre-push-${vp.name}.png`) });
  await ctx.close();
  return { fails, warns, today: info.today, links: info.links.length };
}

(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch();
  let failed = false;
  try {
    for (const vp of VIEWPORTS) {
      const r = await checkViewport(browser, base, vp);
      failed = failed || r.fails.length > 0;
      console.log(`\n${r.fails.length ? "FAIL" : "PASS"}  ${vp.name} ${vp.width}x${vp.height}  (landed on ${r.today || "-"}, ${r.links} show links checked)`);
      r.fails.forEach((f) => console.log("  ✗ " + f));
      [...new Set(r.warns)].forEach((w) => console.log("  ! " + w));
    }
  } finally {
    await browser.close();
    server.close();
  }
  console.log(`\nScreenshots: ${require("os").tmpdir()}/pre-push-phone.png, pre-push-desktop.png`);
  console.log(failed ? "\nPre-push check FAILED." : "\nPre-push check passed.");
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); server.close(); process.exit(1); });
