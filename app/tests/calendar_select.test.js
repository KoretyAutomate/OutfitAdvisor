/**
 * calendar_select.test.js — choosing which calendars to sync (user, 2026-08-14).
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * The rule being pinned is EMPTY MEANS ALL. Getting it backwards would make a
 * fresh install scan nothing and report "no upcoming trips" forever — a silent,
 * plausible, permanent wrong answer, and the user's own calendar would look like
 * the thing at fault. The same trap sits inside the picker: since an empty set
 * means everything, naively removing one id from it turns "not the holidays
 * calendar" into "every calendar".
 *
 * Run: NODE_PATH=<...>/node_modules node tests/calendar_select.test.js
 */

const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
let passed = 0, failed = 0;
const check = (name, cond, detail = "") => {
  if (cond) { passed++; console.log(`[PASS] ${name}`); }
  else { failed++; console.log(`[FAIL] ${name}  ${JSON.stringify(detail)}`); }
};

const dom = new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
});
const w = dom.window;
const ev = (c) => w.eval(c);
const drain = () => new Promise(r => setTimeout(r, 0));

/** Which page an element sits on, read from the DOM rather than assumed. */
const pageOf = (id) => {
  const el = w.document.getElementById(id);
  const v = el && el.closest(".view");
  return v ? v.dataset.v : null;
};

(async () => {
  for (let i = 0; i < 20 && !ev("state.baseUrl"); i++) await drain();
  await new Promise(r => setTimeout(r, 30));

  console.log("\n--- 1. choosing calendars: empty means ALL ------------------------");
  check("the picker is a setting, so it lives behind the gear",
    pageOf("calList") === "settings", pageOf("calList"));
  const CALS = [{ id: "c1", title: "Personal", color: "#38bdf8" },
                { id: "c2", title: "Work", color: "#818cf8" },
                { id: "c3", title: "Holidays in Japan", color: "#fbbf24" }];
  ev(`calendars=${JSON.stringify(CALS)}; calSelected=new Set(); renderCalendars();`);
  check("with nothing chosen, every calendar reads as on",
    w.document.querySelectorAll("#calList input:checked").length === 3);
  check("and the summary says so, rather than showing a count",
    /all 3 calendars/.test(w.document.getElementById("calSummary").textContent),
    w.document.getElementById("calSummary").textContent);

  console.log("\n--- 2. unticking one does not mean 'only this one' ----------------");
  // The trap: an empty set means ALL, so naively removing an id from it would leave
  // it empty — i.e. would turn "not the holidays calendar" into "all of them".
  ev(`document.querySelector('#calList input[data-cal="c3"]').click()`);
  for (let i = 0; i < 6; i++) await drain();
  check("the other two are now an explicit selection",
    JSON.stringify([...ev("calSelected")].sort()) === '["c1","c2"]', [...ev("calSelected")]);
  check("the unticked one stays unticked after the repaint",
    !w.document.querySelector('#calList input[data-cal="c3"]').checked);
  check("and it is persisted",
    (w.localStorage.getItem("oa.calendars") || "").includes("c1"),
    w.localStorage.getItem("oa.calendars"));

  console.log("\n--- 3. the scan reads only the chosen calendars -------------------");
  const EVENTS = [
    { id: "e1", calendarId: "c1", title: "Osaka", startDate: Date.now() + 86400000,
      endDate: Date.now() + 3 * 86400000, isAllDay: false, location: "Hotel" },
    { id: "e2", calendarId: "c2", title: "Conference", startDate: Date.now() + 5 * 86400000,
      endDate: Date.now() + 7 * 86400000, isAllDay: false, location: "Venue" },
    { id: "e3", calendarId: "c3", title: "Golden Week", startDate: Date.now() + 9 * 86400000,
      endDate: Date.now() + 12 * 86400000, isAllDay: true, location: "" },
  ];
  ev(`Plugins.CapacitorCalendar={
        checkPermission: async()=>({result:"granted"}),
        listEventsInRange: async()=>({result:${JSON.stringify(EVENTS)}}),
        listCalendars: async()=>({result:${JSON.stringify(CALS)}})
      };
      trips=[]; tripsDismissed=[]; home=null;`);   // home=null -> every candidate is "ask", no network
  let d = await ev("scanCalendar()");
  check("the deselected calendar's event never becomes a candidate",
    ev(`candidates.map(c=>c.calId).sort().join(",")`) === "e1,e2",
    ev("candidates.map(c=>c.calId)"));
  check("and the two chosen ones do", d.asked === 2, d);

  ev(`calSelected=new Set(); trips=[]; tripsDismissed=[];`);
  d = await ev("scanCalendar()");
  check("clearing the selection goes back to reading everything",
    ev(`candidates.length`) === 3, ev("candidates.length"));

  console.log("\n--- 4. a calendar removed from the phone is forgotten -------------");
  ev(`calSelected=new Set(["c1","c2","gone"]);`);
  await ev("loadCalendars()");
  for (let i = 0; i < 6; i++) await drain();
  check("a stale id is pruned, not left to narrow every future scan",
    JSON.stringify([...ev("calSelected")].sort()) === '["c1","c2"]', [...ev("calSelected")]);
  check("the picker lists what the device actually has",
    w.document.querySelectorAll("#calList .calRow").length === 3);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
