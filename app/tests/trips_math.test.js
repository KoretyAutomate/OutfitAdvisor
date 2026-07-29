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
 * Run: node tests/trips_math.test.js
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
