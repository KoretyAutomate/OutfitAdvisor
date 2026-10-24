/**
 * closet_export.test.js — "Share my closet with an AI" (user, 2026-10-24).
 *
 * "export a file which I can give to LLM my closet and typical weekly schedule +
 * occasions it needs to be aware of" — the routine AI-written from the calendar.
 * Then: "calendar shall be skipped and more generalized e.g., dinner X times in
 * average per month, business trip every X frequency". What matters: the calendar is
 * read as OCCURRENCES (a weekly series begun months ago is in it), only the ticked
 * calendars are asked for at all, and it is COUNTED on the phone — how often, which
 * weekdays, time of day, nights away, online; no date or place leaves. The whole wardrobe goes with
 * the laundry marked, the file reaches the share sheet, and a calendar that cannot be
 * read never stops the export.
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
const iso = (t) => { const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const monday = (t) => { const d = new Date(t); d.setHours(12); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };

/** One occurrence as OutfitAlarm.listInstances returns it. */
function inst(o) {
  const begin = o.begin, end = o.end ?? begin + 3600e3, d = new Date(begin);
  return { eventId: o.eventId, title: o.title, begin, end, allDay: !!o.allDay, location: o.location || "",
    calendarId: o.calendarId || "c1", recurring: !!o.recurring, day: o.day || iso(begin),
    endDay: o.endDay || o.day || iso(o.allDay ? end - 1 : end), weekday: d.getDay(),
    time: o.allDay ? "" : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`,
    week: monday(begin) };
}
function at(daysFromNow, h, m = 0) {
  const d = new Date(Date.now() + daysFromNow * DAY); d.setHours(h, m, 0, 0); return d.getTime();
}

(async () => {
  await ev("appReady");
  const now = Date.now();
  const list = [];
  // A weekly gym SERIES: five occurrences of one recurring event.
  for (let k = -4; k <= 0; k++) list.push(inst({ eventId: "gym", title: "Gym", recurring: true,
    begin: at(k * 7 - 1, 18, 30), end: at(k * 7 - 1, 19, 30), location: "Club" }));
  // The same non-recurring title in two different past weeks: a habit.
  list.push(inst({ eventId: "s1", title: "Squash with Ken", begin: at(-15, 7), end: at(-15, 8) }));
  list.push(inst({ eventId: "s2", title: "squash with ken ", begin: at(-8, 7), end: at(-8, 8) }));
  // Two future appointments a week apart: not a routine — two dated entries.
  list.push(inst({ eventId: "d1", title: "Dentist", begin: at(2, 9), end: at(2, 9, 30), location: "Uptown" }));
  list.push(inst({ eventId: "d2", title: "Dentist", begin: at(9, 9), end: at(9, 11), location: "Downtown" }));
  // A one-off dinner, and a four-day conference with the native layer's own dates.
  list.push(inst({ eventId: "x1", title: "Dinner with Tanaka team", begin: at(6, 19), end: at(6, 21, 30),
    location: "Nobu" }));
  list.push(inst({ eventId: "t1", title: "Chicago conference", allDay: true, begin: at(4, 0), end: at(8, 0),
    day: iso(at(4, 12)), endDay: iso(at(7, 12)) }));
  w.__inst = list;

  console.log("\n--- 1. the calendar, COUNTED — never an entry -------------------");
  const digest = ev(`calDigest(__inst)`);
  const gym = digest.find(e => e.title === "Gym");
  check("a recurring series is one group, counted", gym && gym.n === 5 && gym.evening === 5, gym);
  check("its weekday counted", gym && gym.weekdays.reduce((a, b) => a + b, 0) === 5
    && Math.max(...gym.weekdays) === 5, gym);
  check("a repeated title is one group", digest.filter(e => /squash/i.test(e.title)).length === 1
    && digest.find(e => /squash/i.test(e.title)).morning === 2, digest);
  const dentist = digest.find(e => e.title === "Dentist");
  check("two appointments are one group of two", dentist && dentist.n === 2, dentist);
  const trip = digest.find(e => /conference/.test(e.title));
  check("a multi-day entry counts its nights away, from the native dates", trip && trip.nights === 3
    && trip.allDay === 1, trip);
  const call = ev(`calDigest([${JSON.stringify(inst({ eventId: "z1", title: "Standup", begin: Date.now(),
    location: "https://zoom.us/j/1" }))}])`)[0];
  check("a video-call place counts as online", call.online === 1, call);
  check("nothing but counts and the title leaves the phone",
    digest.every(e => Object.keys(e).sort().join() ===
      "afternoon,allDay,evening,morning,n,nights,online,title,weekdays"), digest[0]);

  console.log("\n--- 2. the export: what is asked for, what is sent, the share sheet -");
  ev(`
    closet=[{id:"itm-a0000001",label:"grey marl sweater",category:"mid",group:"tops",type:"sweater",
             roles:["mid"],colors:["grey"],warmth:4,count:1},
            {id:"itm-b0000001",label:"olive parka",category:"outer",group:"outerwear",type:"coat",
             roles:["outer"],colors:["olive"],warmth:4,count:1}];
    wearLog=[{itemId:"itm-a0000001",wornAt:Date.now()-3600e3}];
    lastWorn={"itm-a0000001":[Date.now()-3600e3]};
    Plugins.OutfitAlarm = { listCalendars: async () => ({calendars:[
        {id:"c1", title:"Personal", account:"me@example.com", shared:false},
        {id:"shared9", title:"Team", account:"me@example.com", shared:true}]}),
      listInstances: async (o) => { globalThis.__asked=o;
        return {instances:[...__inst, {eventId:"z", title:"Someone else's thing",
          begin:Date.now()+DAY_MS, end:Date.now()+DAY_MS+3600e3, calendarId:"shared9", day:"2099-01-01",
          endDay:"2099-01-01", week:"2098-12-29", weekday:4, time:"12:00"}]}; } };
    Plugins.CapacitorCalendar = { checkPermission: async () => ({result:"granted"}) };
    calMode="all"; calSel=[]; calShared=[];
    globalThis.__sent=null; globalThis.__shared=null; globalThis.__written=null;
    fetch = async (url, opts) => { globalThis.__url=url; globalThis.__sent=JSON.parse(opts.body);
      return {ok:true, status:200, json: async () => ({markdown:"# My closet", filename:"my-closet-x.md", routine:true})}; };
    Plugins.Filesystem = { ...(Plugins.Filesystem||{}), writeFile: async (o) => { globalThis.__written=o; return {uri:"file:///cache/"+o.path}; } };
    Plugins.Share = { share: async (o) => { globalThis.__shared=o; } };
  `);
  await ev("shareCloset()");
  const asked = ev("__asked"), sent = ev("__sent");
  check("only the ticked calendars are asked for", JSON.stringify(asked.calendarIds) === JSON.stringify(["c1"]), asked);
  check("twelve weeks back, nothing ahead", Math.round((asked.to - asked.from) / DAY) === 84
    && asked.to <= now, asked);
  check("and an unticked calendar's entry is dropped even if the native layer returned it",
    !sent.events.some(e => /Someone else/.test(e.title)), sent.events);
  check("it posts to /export", /\/export$/.test(ev("__url")), ev("__url"));
  check("the WHOLE wardrobe goes, the laundry marked", sent.closet.length === 2
    && JSON.stringify(sent.laundry) === JSON.stringify(["itm-a0000001"]), sent.laundry);
  check("with the wear history in days", sent.recent["itm-a0000001"] === 0, sent.recent);
  check("the counted groups, not the raw occurrences", sent.calendar === true && sent.days === 84
    && sent.events.filter(e => e.title === "Gym").length === 1 && !sent.events.some(e => "day" in e), sent.events);
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
