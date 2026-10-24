/**
 * closet_export.test.js — "Share my closet with an AI" (user, 2026-10-24).
 *
 * "export a file which I can give to LLM my closet and typical weekly schedule +
 * occasions it needs to be aware of" — the routine AI-written from the calendar.
 * What matters: the calendar is boiled down to PATTERNS on the phone (a weekly gym
 * session is one line, not four events), only ticked calendars are read, the whole
 * wardrobe goes with the laundry marked, and the file reaches the share sheet. A
 * calendar that cannot be read never stops the export.
 *
 * Run: npm test   (or: node tests/closet_export.test.js)
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
const DAY = 864e5;

function at(daysFromNow, h, m = 0) {
  const d = new Date(Date.now() + daysFromNow * DAY); d.setHours(h, m, 0, 0); return d.getTime();
}

(async () => {
  await ev("appReady");
  const now = Date.now();
  // A gym session on the same weekday for five weeks, a one-off dinner next week,
  // and a past one-off that says nothing about the future.
  const events = [];
  for (let k = -4; k <= 0; k++) events.push({ id: `g${k}`, calendarId: "c1", title: "Gym ", isAllDay: false,
    startDate: at(k * 7 - 1, 18, 30), endDate: at(k * 7 - 1, 19, 30), location: "Club" });
  events.push({ id: "d1", calendarId: "c1", title: "Dinner with Tanaka team", isAllDay: false,
    startDate: at(6, 19), endDate: at(6, 21, 30), location: "Nobu" });
  events.push({ id: "p1", calendarId: "c1", title: "Dentist", isAllDay: false,
    startDate: at(-10, 9), endDate: at(-10, 10) });
  events.push({ id: "s1", calendarId: "shared9", title: "Someone else's thing", isAllDay: false,
    startDate: at(3, 12), endDate: at(3, 13) });
  w.__events = events;

  console.log("\n--- 1. the calendar, boiled down to patterns ----------------------");
  const digest = ev(`calDigest(__events.filter(e=>e.calendarId==="c1"), ${now})`);
  const gym = digest.find(e => e.title.trim() === "Gym");
  check("a weekly session is ONE recurring line", digest.filter(e => /gym/i.test(e.title)).length === 1, digest);
  check("with its weekday, time, length and weeks", gym && gym.weekdays.length === 1 && gym.start === "18:30"
    && gym.minutes === 60 && gym.weeks >= 3 && !gym.date, gym);
  const dinner = digest.find(e => /Dinner/.test(e.title));
  check("a one-off coming up keeps its date", dinner && dinner.date && dinner.start === "19:00"
    && dinner.minutes === 150 && dinner.location === "Nobu", dinner);
  check("a past one-off is dropped", !digest.some(e => /Dentist/.test(e.title)), digest);

  console.log("\n--- 2. the export: what is sent, and the share sheet --------------");
  ev(`
    closet=[{id:"itm-a0000001",label:"grey marl sweater",category:"mid",group:"tops",type:"sweater",
             roles:["mid"],colors:["grey"],warmth:4,count:1},
            {id:"itm-b0000001",label:"olive parka",category:"outer",group:"outerwear",type:"coat",
             roles:["outer"],colors:["olive"],warmth:4,count:1}];
    wearLog=[{itemId:"itm-a0000001",wornAt:Date.now()-3600e3}];
    lastWorn={"itm-a0000001":[Date.now()-3600e3]};
    Plugins.OutfitAlarm = { listCalendars: async () => ({calendars:[
      {id:"c1", title:"Personal", account:"me@example.com", shared:false},
      {id:"shared9", title:"Team", account:"me@example.com", shared:true}]}) };
    Plugins.CapacitorCalendar = { checkPermission: async () => ({result:"granted"}),
      listEventsInRange: async ({startDate,endDate}) => { globalThis.__range=[startDate,endDate];
        return {result:__events}; } };
    calMode="all"; calSel=[]; calShared=[];
    globalThis.__sent=null; globalThis.__shared=null; globalThis.__written=null;
    fetch = async (url, opts) => { globalThis.__url=url; globalThis.__sent=JSON.parse(opts.body);
      return {ok:true, status:200, json: async () => ({markdown:"# My closet", filename:"my-closet-x.md", routine:true})}; };
    Plugins.Filesystem = { ...(Plugins.Filesystem||{}), writeFile: async (o) => { globalThis.__written=o; return {uri:"file:///cache/"+o.path}; } };
    Plugins.Share = { share: async (o) => { globalThis.__shared=o; } };
  `);
  await ev("shareCloset()");
  const sent = ev("__sent");
  check("it posts to /export", /\/export$/.test(ev("__url")), ev("__url"));
  check("the WHOLE wardrobe goes, the laundry marked", sent.closet.length === 2
    && JSON.stringify(sent.laundry) === JSON.stringify(["itm-a0000001"]), sent.laundry);
  check("with the wear history in days", sent.recent["itm-a0000001"] === 0, sent.recent);
  check("a shared calendar that is not ticked is never read",
    !sent.events.some(e => /Someone else/.test(e.title)), sent.events);
  check("the digest, not the raw events", sent.calendar === true
    && sent.events.filter(e => /gym/i.test(e.title)).length === 1, sent.events);
  const [from, to] = ev("__range");
  check("four weeks back, two ahead", Math.round((now - from) / DAY) === 28 && Math.round((to - now) / DAY) === 14,
    [from, to]);
  check("the file is written and handed to the share sheet",
    ev("__written").path === "my-closet-x.md" && ev("__written").data === "# My closet"
    && ev("__shared").files[0] === "file:///cache/my-closet-x.md", ev("__shared"));

  console.log("\n--- 3. no calendar never stops the export --------------------------");
  ev(`Plugins.CapacitorCalendar = { checkPermission: async () => ({result:"denied"}),
        requestPermission: async () => ({result:"denied"}) }; __sent=null;`);
  await ev("shareCloset()");
  const s2 = ev("__sent");
  check("sent with calendar:false and no events", s2 && s2.calendar === false && s2.events.length === 0, s2);
  check("and the note says so", /No calendar was readable/.test(w.document.getElementById("exportNote").textContent),
    w.document.getElementById("exportNote").textContent);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
