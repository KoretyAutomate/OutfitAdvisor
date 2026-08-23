/**
 * trips_math.test.js — T2/T2.5 verification.
 *
 * Loads the REAL app/www/index.html in jsdom and exercises the trip functions in
 * place, so this cannot drift from the shipped code the way a copy-pasted copy of
 * the math would. State (`closet`, `wearLog`, `trips`) is declared with `let`, so
 * it lives in the page's global lexical scope, not on `window` — we reach it via a
 * global eval rather than adding test-only hooks to production code.
 *
 * The two things under test are the ones plan review flagged as most likely to be
 * silently wrong:
 *   T-2  packAvail projects the laundry cooldown forward to DEPARTURE, and an
 *        explicit "I'll do laundry first" makes everything packable again.
 *   T-1  closetPayload sends ONLY what is in the suitcase while you are away —
 *        without it the morning push recommends the coat you left at home.
 *
 * Run: npm test   (or: node tests/trips_math.test.js — jsdom is a devDependency since 2026-08-20)
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
const DAY = 86400000;

let passed = 0, failed = 0;
const check = (name, cond, detail = "") => {
  if (cond) { passed++; console.log(`[PASS] ${name}`); }
  else { failed++; console.log(`[FAIL] ${name}  ${JSON.stringify(detail)}`); }
};

const dom = new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously",
  url: "https://localhost/",
  pretendToBeVisual: true,
});
const w = dom.window;
// Indirect eval -> runs in the page's global scope, which can see its top-level
// `let` bindings. This is how we set up state without touching production code.
const ev = (code) => w.eval(code);
const evj = (expr) => JSON.parse(w.eval(`JSON.stringify(${expr})`));

setTimeout(() => {
  try { run(); } catch (e) { console.log("FATAL", e && e.stack || e); failed++; }
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
}, 400);

const iso = (off) => {
  const d = new Date(Date.now() + off * DAY);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function run() {
  console.log(`Trips math (T2/T2.5) — ${new Date().toISOString()}`);
  console.log("Source: exercised in-place in app/www/index.html via jsdom\n");

  check("page exposes the trip functions",
    ev("typeof packAvail==='function' && typeof closetPayload==='function' && " +
       "typeof toCandidate==='function' && typeof tripInProgress==='function'"));

  // ---------------------------------------- T-2: cooldown projected to departure
  console.log("\n-- T-2: cooldown is projected forward to DEPARTURE --");
  ev(`closet.length=0;
      closet.push({id:'t1',label:'tee',category:'base',colors:[],warmth:1,
                   formality:['casual'],waterproof:false,count:2});
      wearLog.length=0;
      wearLog.push({itemId:'t1',wornAt:Date.now()});
      wearLog.push({itemId:'t1',wornAt:Date.now()-86400000});
      trips.length=0;`);

  check("as of NOW, both wears bite -> 0 of 2 available",
    ev("avail(closet[0])") === 0, ev("avail(closet[0])"));

  check("departing in 5 days -> both wears have expired -> 2 packable",
    ev("packAvail(closet[0], Date.now()+5*86400000, false)") === 2,
    ev("packAvail(closet[0], Date.now()+5*86400000, false)"));

  check("departing TOMORROW -> cooldown still bites -> 0 packable",
    ev("packAvail(closet[0], Date.now()+86400000, false)") === 0,
    ev("packAvail(closet[0], Date.now()+86400000, false)"));

  // The case that made the first formula wrong: one wash tonight fixes it, and the
  // model had no way to express that, so it declared your favourite shirt unpackable.
  check("departing TOMORROW + 'I'll do laundry first' -> 2 packable again",
    ev("packAvail(closet[0], Date.now()+86400000, true)") === 2,
    ev("packAvail(closet[0], Date.now()+86400000, true)"));

  check("packAvail never goes negative",
    ev("packAvail({id:'t1',count:1}, Date.now(), false)") >= 0);

  // -------------------------------- T-1: suitcase-aware daily advice (the big one)
  console.log("\n-- T-1: while away, dress from the SUITCASE, not the wardrobe --");
  ev(`closet.length=0;
      closet.push({id:'shirt',label:'oxford',category:'base',colors:[],warmth:2,
                   formality:['smart'],waterproof:false,count:3});
      closet.push({id:'coat',label:'winter coat',category:'outer',colors:[],warmth:5,
                   formality:['casual'],waterproof:false,count:1});
      wearLog.length=0; trips.length=0;`);

  check("no trip: the whole wardrobe is offered",
    JSON.stringify(evj("closetPayload().map(i=>i.id).sort()")) ===
    JSON.stringify(["coat", "shirt"]),
    evj("closetPayload().map(i=>i.id)"));

  // an ACTIVE trip with only 2 of the 3 shirts packed, and the coat left at home
  ev(`trips.push({id:'trp1',start:'${iso(-1)}',end:'${iso(2)}',lat:0,lon:0,
       place:'Osaka',type:'business',styles:['smart'],notifyDays:2,
       packed:[{id:'shirt',qty:2}]});`);

  check("tripInProgress finds the active trip", ev("!!tripInProgress()"));

  const ids = evj("closetPayload().map(i=>i.id)");
  check("while away, the coat left AT HOME is not offered", !ids.includes("coat"), ids);
  check("while away, the packed shirt IS offered", ids.includes("shirt"), ids);
  check("while away, quantity is capped at what was PACKED (2, not the 3 owned)",
    ev("closetPayload().find(i=>i.id==='shirt').availableCount") === 2,
    ev("closetPayload().find(i=>i.id==='shirt').availableCount"));

  ev("logWear('shirt')");
  check("wearing it on the trip consumes from the SUITCASE (2 -> 1)",
    ev("closetPayload().find(i=>i.id==='shirt').availableCount") === 1,
    ev("closetPayload().find(i=>i.id==='shirt').availableCount"));

  ev(`trips[0].start='${iso(-4)}'; trips[0].end='${iso(-1)}';`);
  check("after the trip ends, the full wardrobe is available again",
    evj("closetPayload().map(i=>i.id)").includes("coat"),
    evj("closetPayload().map(i=>i.id)"));

  ev(`trips.length=0; wearLog.length=0;
      trips.push({id:'trp2',start:'${iso(0)}',end:'${iso(3)}',packed:[]});`);
  check("an active trip with NOTHING packed yet does not starve the daily advice",
    ev("closetPayload().length") === 2, ev("closetPayload().length"));

  // ------------------------------------------------------ candidate detection
  console.log("\n-- candidate detection --");
  const D = (s) => new Date(s).getTime();

  check("multi-day all-day event IS a trip",
    ev(`!!toCandidate({id:'e1',title:'Osaka offsite',isAllDay:true,
        startDate:${D("2026-08-03T00:00")},endDate:${D("2026-08-06T00:00")}})`));

  // The trap: all-day events end at EXCLUSIVE midnight, so a birthday looks like it
  // spans a night unless you step back 1ms first.
  check("single-day all-day event (a birthday) is NOT a trip",
    ev(`toCandidate({id:'e2',title:'Dad birthday',isAllDay:true,
        startDate:${D("2026-08-03T00:00")},endDate:${D("2026-08-04T00:00")}})`) === null);

  check("a 1-hour standup is NOT a trip",
    ev(`toCandidate({id:'e3',title:'Standup',isAllDay:false,
        startDate:${D("2026-08-03T09:00")},endDate:${D("2026-08-03T10:00")}})`) === null);

  check("an overnight timed event IS a trip",
    ev(`!!toCandidate({id:'e4',title:'Red-eye',isAllDay:false,
        startDate:${D("2026-08-03T22:00")},endDate:${D("2026-08-05T09:00")}})`));

  check("a 2-month block is NOT a trip",
    ev(`toCandidate({id:'e5',title:'Q3',isAllDay:true,
        startDate:${D("2026-08-01T00:00")},endDate:${D("2026-10-01T00:00")}})`) === null);

  const c = evj(`toCandidate({id:'e6',title:'Client visit',isAllDay:true,
      location:'Marriott Downtown Chicago',description:'bring the deck',
      organizer:'someone@corp.com',
      startDate:${D("2026-08-03T00:00")},endDate:${D("2026-08-06T00:00")}})`);
  check("the raw calendar location is kept only as a HINT (never auto-geocoded)",
    c.hint === "Marriott Downtown Chicago", c);
  check("notes/organizer are dropped — data we never read cannot leak",
    !("description" in c) && !("organizer" in c), Object.keys(c));
}

/* ── scanCalendar must call the plugin the way the plugin actually works ──
   This boundary was never crossed by a test. The suite covered toCandidate (the
   pure event->candidate mapping) and stopped there, so scanCalendar could pass
   {from,to} to a plugin whose signature is {startDate,endDate} and nothing
   noticed. The real plugin received undefined for both, so the calendar scan
   could not have worked on a device at all (found 2026-08-13).

   The fake below mirrors the REAL contract from @ebarooni/capacitor-calendar's
   definitions.d.ts and throws on anything else, so this can only pass if the app
   speaks the plugin's language.

   These blocks share page globals, so they run in sequence rather than as loose
   IIFEs — since 2026-08-19 scanCalendar awaits the native calendar list too, and
   interleaved blocks would reset each other's stubs mid-scan. */
async function pluginSignatureChecks() {
  ev(`Plugins.OutfitAlarm = Object.assign(Plugins.OutfitAlarm || {}, {
    listCalendars: async () => ({ calendars: [{ id: "work", title: "Work", shared: false }] })
  });
  Plugins.CapacitorCalendar = {
    checkPermission: async () => ({ result: "granted" }),
    requestPermission: async () => ({ result: "granted" }),
    listEventsInRange: async (o) => {
      if (typeof o.startDate !== "number" || typeof o.endDate !== "number") {
        throw new Error("plugin needs {startDate,endDate}; got " + JSON.stringify(Object.keys(o)));
      }
      globalThis.__calArgs = o;
      return { result: [] };
    }
  }; trips=[]; tripsDismissed=[]; calMode="all"; calSel=[];`);
  let err = null;
  try { await ev("scanCalendar()"); } catch (e) { err = e; }
  check("scanCalendar calls the plugin with the signature it really has",
    err === null, err && err.message);
  const a = ev("globalThis.__calArgs") || {};
  check("it sends startDate/endDate, never from/to",
    typeof a.startDate === "number" && typeof a.endDate === "number" &&
    a.from === undefined && a.to === undefined, a);
  check("and scans a TRIP_SCAN_DAYS-wide window",
    Math.round((a.endDate - a.startDate) / 86400000) === ev("TRIP_SCAN_DAYS"), a);
}

/* ── the calendar picker actually narrows what gets scanned ──
   PLAN amendment T-8 asked for this and it was never built, so the scan read
   EVERY calendar the OS exposes — birthdays, holidays, subscribed feeds — and the
   user got trip candidates they did not recognise (2026-08-16). READ_CALENDAR is
   all-or-nothing, so filtering by calendarId is the only minimum-privilege
   control available on top of it.

   Two rules are pinned here, and the SHARED one is not a preference: a calendar
   somebody else shared with this account is never read, whatever the saved
   selection says (user rule, 2026-08-19). */
const PICKER_EVENTS = [
  { id: "work-1", calendarId: "work", title: "Client visit", isAllDay: true,
    location: "Marriott Downtown Chicago",
    startDate: Date.parse("2026-09-02T00:00"), endDate: Date.parse("2026-09-05T00:00") },
  { id: "hol-1", calendarId: "holidays", title: "Labor Day", isAllDay: true,
    startDate: Date.parse("2026-09-07T00:00"), endDate: Date.parse("2026-09-09T00:00") },
  { id: "bday-1", calendarId: "birthdays", title: "Sam's birthday", isAllDay: true,
    startDate: Date.parse("2026-09-10T00:00"), endDate: Date.parse("2026-09-12T00:00") },
  // Shared into this account by a partner. Nothing on it may ever be read.
  { id: "shared-1", calendarId: "partner", title: "Barcelona", isAllDay: true,
    startDate: Date.parse("2026-09-14T00:00"), endDate: Date.parse("2026-09-18T00:00") },
];

async function pickerChecks() {
  ev(`Plugins.OutfitAlarm = Object.assign(Plugins.OutfitAlarm || {}, {
    listCalendars: async () => ({ calendars: [
      {id:"work",title:"Personal",account:"korehito@gmail.com",shared:false},
      {id:"holidays",title:"US Holidays",account:"feeds@partner.example",shared:false},
      {id:"birthdays",title:"Birthdays",account:"korehito@gmail.com",shared:false},
      {id:"partner",title:"Alex's calendar",account:"korehito@gmail.com",
       shared:true,sharedBy:"alex@example.com"}] })
  });
  Plugins.CapacitorCalendar = {
    checkPermission: async () => ({ result: "granted" }),
    requestPermission: async () => ({ result: "granted" }),
    listEventsInRange: async () => ({ result: ${JSON.stringify(PICKER_EVENTS)} })
  };
  // no home + unreachable advisor => every survivor lands in "ask", so what the
  // filter let through is exactly what we can count.
  home = null; trips = []; tripsDismissed = []; candidates = [];`);

  const rescan = async (setup) => {
    ev(`trips=[]; tripsDismissed=[]; candidates=[]; ${setup}`);
    let err = null;
    try { await ev("scanCalendar()"); } catch (e) { err = e; }
    return err;
  };

  await rescan(`calMode="all"; calSel=[];`);
  check("with no selection, every calendar the user OWNS is scanned",
    JSON.stringify(ev("candidates.map(c=>c.calId)").sort()) === '["bday-1","hol-1","work-1"]',
    ev("candidates.map(c=>c.calId)"));

  await rescan(`calMode="some"; calSel=["work"];`);
  check("selecting one calendar excludes the others",
    ev("candidates.length") === 1 && ev("candidates[0].calId") === "work-1",
    ev("candidates.map(c=>c.calId)"));

  await rescan(`calMode="some"; calSel=["work","birthdays"];`);
  check("selecting several includes exactly those",
    JSON.stringify(ev("candidates.map(c=>c.calId)").sort()) === '["bday-1","work-1"]',
    ev("candidates.map(c=>c.calId)"));

  /* ── a shared calendar is never read (2026-08-19) ──
     Not a default the user can override: the allow-list is rebuilt from the
     device each scan, so even an id saved while the calendar was still the
     user's own cannot get it read. */
  await rescan(`calMode="all"; calSel=[];`);
  check("a shared calendar is not scanned even with no filter set",
    !ev("candidates.map(c=>c.calId)").includes("shared-1"),
    ev("candidates.map(c=>c.calId)"));

  let err = await rescan(`calMode="some"; calSel=["partner"];`);
  check("a stale selection naming a shared calendar reads NOTHING, not everything",
    ev("candidates.length") === 0 && !!err, [err && err.message, ev("candidates.map(c=>c.calId)")]);

  /* ── Unselect all means read nothing (2026-08-19) ──
     The old encoding made an empty list mean "all", so unticking every box would
     have scanned every calendar — the exact opposite of the request. */
  err = await rescan(`calMode="none"; calSel=[];`);
  check("mode none scans no calendar at all",
    ev("candidates.length") === 0 && !!err, [err && err.message, ev("candidates.map(c=>c.calId)")]);
  check("and it says so instead of failing silently",
    !!err && /no calendars are selected/i.test(err.message), err && err.message);

  /* ── failing closed ──
     Without the native lister we cannot tell a shared calendar from the user's
     own, so the scan must stop rather than fall back to reading everything. */
  ev(`globalThis.__savedLister = Plugins.OutfitAlarm.listCalendars;
      delete Plugins.OutfitAlarm.listCalendars;`);
  err = await rescan(`calMode="all"; calSel=[];`);
  check("with no way to tell shared from own, nothing is scanned",
    ev("candidates.length") === 0 && !!err, [err && err.message, ev("candidates.map(c=>c.calId)")]);
  ev(`Plugins.OutfitAlarm.listCalendars = globalThis.__savedLister;`);

  /* ── what the picker's two buttons store ── */
  const boxes = (checked) => ev(`calAvail=[{id:"work",title:"Work",shared:false},
        {id:"holidays",title:"US Holidays",shared:false}];
      document.getElementById("calList").innerHTML =
        '<input type="checkbox" data-cal="work" ${checked ? "checked" : ""}>' +
        '<input type="checkbox" data-cal="holidays" ${checked ? "checked" : ""}>';`);

  // Ticking everything must not freeze a list, or a calendar added later would be
  // silently excluded forever.
  boxes(true);
  await ev("saveCalSel()");
  check("Select all stores mode=all (no frozen list), so future calendars count too",
    ev("calMode") === "all" && ev("calSel.length") === 0, [ev("calMode"), ev("calSel")]);

  boxes(false);
  await ev("saveCalSel()");
  check("Unselect all stores mode=none — an empty tick list is not 'read them all'",
    ev("calMode") === "none" && ev("calSel.length") === 0, [ev("calMode"), ev("calSel")]);

  // A picker that could not list anything shows no boxes; saving then must not
  // overwrite a real selection with an empty one the user never made.
  ev(`calMode="some"; calSel=["work"]; document.getElementById("calList").innerHTML="";`);
  await ev("saveCalSel()");
  check("saving an empty picker leaves the existing selection alone",
    ev("calMode") === "some" && ev("calSel[0]") === "work", [ev("calMode"), ev("calSel")]);

  /* ── the shared ones are shown, greyed, so an exclusion is visible ── */
  await ev("openCalPicker()");
  const html = ev(`document.getElementById("calList").innerHTML`);
  check("the picker offers a checkbox for each calendar the user owns",
    (html.match(/data-cal=/g) || []).length === 3, (html.match(/data-cal="[^"]+"/g) || []));
  check("and lists the shared one as un-tickable, saying why",
    html.includes("Alex's calendar") && !html.includes('data-cal="partner"') &&
    /never read/.test(html), html.slice(0, 400));

  /* ── the list is HIERARCHICAL: account first, its calendars underneath
        (user, 2026-08-20). A flat list of "Personal", "Birthdays", "US Holidays"
        never says which sign-in each one came from. ── */
  const heads = [...html.matchAll(/📧 ([^<]+)</g)].map(m => m[1].trim());
  check("every account the calendars belong to gets its own heading",
    JSON.stringify(heads) === '["korehito@gmail.com","feeds@partner.example"]', heads);
  check("the account with the most readable calendars leads",
    heads[0] === "korehito@gmail.com", heads);
  const at = (needle) => html.indexOf(needle);
  check("a calendar sits under ITS OWN account, not in one flat list",
    at("korehito@gmail.com") < at("Personal") &&
    at("Personal") < at("feeds@partner.example") &&
    at("feeds@partner.example") < at("US Holidays"),
    [at("korehito@gmail.com"), at("Personal"), at("feeds@partner.example"), at("US Holidays")]);
  check("a shared calendar stays under the account it was shared INTO",
    at("Alex's calendar") > at("korehito@gmail.com") &&
    at("Alex's calendar") < at("feeds@partner.example"),
    [at("korehito@gmail.com"), at("Alex's calendar"), at("feeds@partner.example")]);
  check("and each heading says how many of its calendars can be read",
    /2 you can read/.test(html) && /1 you can read/.test(html), heads);

  // A device calendar with no account at all must still land somewhere named.
  ev(`calAvail=[{id:"local",title:"My calendar",account:"",shared:false}];`);
  const solo = ev(`calGroups()`);
  check("a calendar with no account is grouped under a heading of its own",
    solo.length === 1 && solo[0].account === "" && solo[0].own === 1, solo);
  check("and the picker names that heading rather than showing a blank line",
    ev(`CAL_NO_ACCOUNT`).length > 0, ev(`CAL_NO_ACCOUNT`));
}

pluginSignatureChecks()
  .then(pickerChecks)
  .catch((e) => { console.log("FATAL", e && e.stack || e); failed++; });
