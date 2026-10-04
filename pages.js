/* Behavior for the generated show and venue pages. The pages work without
   this script; it adds save, calendar, share and "already happened". */
(function () {
  "use strict";
  var body = document.body;
  function $(id) { return document.getElementById(id); }

  /* Today's date in New York as YYYY-MM-DD; the night runs until 4 AM. */
  function nyToday() {
    var d;
    try {
      var o = {};
      new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York", year: "numeric", month: "numeric",
        day: "numeric", hour: "numeric", hourCycle: "h23"
      }).formatToParts(new Date()).forEach(function (p) { o[p.type] = parseInt(p.value, 10); });
      d = new Date(Date.UTC(o.year, o.month - 1, o.day, o.hour % 24));
    } catch (e) {
      var n = new Date();
      d = new Date(Date.UTC(n.getFullYear(), n.getMonth(), n.getDate(), n.getHours()));
    }
    d.setUTCHours(d.getUTCHours() - 4);
    return d.toISOString().slice(0, 10);
  }
  var today = nyToday();

  // Dim rows for shows that have already happened.
  var rows = document.querySelectorAll("li[data-date]");
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].getAttribute("data-date") < today) rows[i].classList.add("past");
  }

  /* ---------- venue page: fold earlier shows ---------- */
  if (body.getAttribute("data-kind") === "venue") {
    var past = document.querySelectorAll("#venueRows li.past");
    var btn = $("earlierBtn");
    if (past.length && past.length < rows.length && btn) {
      var open = false;
      var paint = function () {
        for (var j = 0; j < past.length; j++) past[j].hidden = !open;
        btn.textContent = open ? "Hide earlier shows" : "Show " + past.length + " earlier " + (past.length === 1 ? "show" : "shows");
      };
      btn.hidden = false;
      btn.addEventListener("click", function () { open = !open; paint(); });
      paint();
      $("venueHead").textContent = "Coming up";
    }
    return;
  }

  /* ---------- show page ---------- */
  // Missed connections make sense once the night has started.
  if (body.getAttribute("data-date") <= today && $("mcLink")) $("mcLink").hidden = false;
  if (body.getAttribute("data-date") < today) {
    $("pastNote").hidden = false;
    // The list may have moved on to another month; don't jump to a day there.
    var back = document.querySelector(".back");
    if (back) back.setAttribute("href", "../");
  }

  // Save: shares its list with the main page (same browser storage key).
  var saveKey = body.getAttribute("data-save-key"), showKey = body.getAttribute("data-show-key");
  function readSaved() {
    try { return JSON.parse(localStorage.getItem(saveKey)) || []; } catch (e) { return []; }
  }
  var saveBtn = $("saveBtn");
  function paintSave() {
    var on = readSaved().indexOf(showKey) !== -1;
    saveBtn.setAttribute("aria-pressed", on ? "true" : "false");
    saveBtn.textContent = on ? "★ Saved" : "☆ Save";
  }
  saveBtn.addEventListener("click", function () {
    var list = readSaved(), at = list.indexOf(showKey);
    if (at === -1) list.push(showKey); else list.splice(at, 1);
    try { localStorage.setItem(saveKey, JSON.stringify(list)); } catch (e) {}
    paintSave();
  });
  paintSave();

  // Share: the phone's share sheet where there is one, otherwise copy the link.
  var shareBtn = $("shareBtn");
  shareBtn.addEventListener("click", function () {
    var data = { title: document.title, url: location.href };
    if (navigator.share) { navigator.share(data).catch(function () {}); return; }
    var done = function (t) {
      shareBtn.textContent = t;
      setTimeout(function () { shareBtn.textContent = "Share"; }, 1800);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(location.href).then(function () { done("Link copied"); }, function () { done("Copy the address bar"); });
    } else done("Copy the address bar");
  });

  // Calendar file for this one show (assumes a 3-hour show).
  function icsText(t) {
    return String(t).replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
  }
  function fold(line) {
    var out = [];
    while (line.length > 73) { out.push(line.slice(0, 73)); line = " " + line.slice(73); }
    out.push(line);
    return out.join("\r\n");
  }
  $("calBtn").addEventListener("click", function () {
    var start = body.getAttribute("data-cal-start");
    var L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Show Me NYC//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT",
      "UID:" + body.getAttribute("data-cal-file") + "@show-me-nyc",
      "DTSTAMP:" + new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+/, "")];
    if (start.indexOf("T") === -1) {
      var y = +start.slice(0, 4), m = +start.slice(4, 6), d = +start.slice(6, 8);
      var next = new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10).replace(/-/g, "");
      L.push("DTSTART;VALUE=DATE:" + start, "DTEND;VALUE=DATE:" + next);
    } else {
      L.push("DTSTART;TZID=America/New_York:" + start, "DURATION:PT3H");
    }
    L.push("SUMMARY:" + icsText(body.getAttribute("data-cal-title")),
      "LOCATION:" + icsText(body.getAttribute("data-cal-venue")),
      "DESCRIPTION:" + icsText(body.getAttribute("data-cal-desc")),
      "URL:" + location.href, "END:VEVENT", "END:VCALENDAR");
    var url = URL.createObjectURL(new Blob([L.map(fold).join("\r\n") + "\r\n"], { type: "text/calendar;charset=utf-8" }));
    var a = document.createElement("a");
    a.href = url;
    a.download = body.getAttribute("data-cal-file");
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  });
})();
