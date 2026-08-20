/**
 * trip_edit.test.js — editing a trip must actually change it (2026-08-20).
 *
 * The Edit button on a trip card is the only route to the trip sheet's Delete and
 * to changing a destination the calendar guessed. Two ways that route can lie:
 *
 *   1. Delete removes the trip but not the calendar event it came from. The event
 *      is then in neither `trips` nor `tripsDismissed`, so the next scan judges it
 *      afresh and puts the same trip straight back — Delete that holds only until
 *      the next scan is worse than no Delete at all.
 *   2. The sheet opens on the trip's OLD lat/lon/place. Retype the city, tap Save
 *      without Find, and the validation passes on the stale coordinates: the trip
 *      is stored under the new name with the old destination, and every forecast
 *      and packing list is for the city the user just edited away from.
 *
 * Both are driven through the real handlers, and 1. is proved by running a second
 * calendar scan over the same event rather than by inspecting a variable.
 *
 * Run: npm test   (or: node tests/trip_edit.test.js — jsdom is a devDependency since 2026-08-20)
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
const doc = w.document;
const ev = (c) => w.eval(c);
const drain = async (n = 8) => { for (let i = 0; i < n; i++) await new Promise(r => setTimeout(r, 0)); };

// One overnight event, on a calendar of the user's own, 30 days out.
const DAY = 864e5;
const START = Date.now() + 30 * DAY;
const CHICAGO = { lat: 41.88, lon: -87.63, place: "Chicago, Illinois, US" };

/** A device whose calendar holds exactly that one event, judged a trip. */
function stubDevice() {
  ev(`
    Plugins.OutfitAlarm = { listCalendars: async () => ({calendars:[
      {id:"c1", title:"Personal", account:"me@example.com", shared:false}]}) };
    Plugins.CapacitorCalendar = {
      checkPermission: async () => ({result:"granted"}),
      listEventsInRange: async () => ({result:[
        {id:"ev-1", calendarId:"c1", title:"Client visit", isAllDay:false,
         location:"Marriott Downtown Chicago",
         startDate:${START}, endDate:${START + 3 * DAY}}]}),
    };
    calMode = "all"; calSel = [];
    triageCandidate = async () => ({decision:"trip", city:"Chicago",
      place:${JSON.stringify(CHICAGO.place)}, lat:${CHICAGO.lat}, lon:${CHICAGO.lon},
      type:"business", km:1099, confidence:.95});
  `);
}

(async () => {
  for (let i = 0; i < 20 && !ev("state.baseUrl"); i++) await drain(1);
  await new Promise(r => setTimeout(r, 30));
  stubDevice();

  console.log("\n--- 1. the scan finds it, so there is something to delete --------");
  ev("trips=[]; tripsDismissed=[]; candidates=[];");
  let d = await ev("scanCalendar()");
  check("one trip was added automatically", d.added === 1 && ev("trips.length") === 1, d);
  check("and it remembers which calendar event it came from",
    ev("trips[0].calId") === "ev-1", ev("trips[0]"));

  console.log("\n--- 2. Edit → Delete, and it stays deleted -----------------------");
  ev(`openTripSheet(trips.find(t=>t.calId==="ev-1"), false, "");`);
  check("the sheet opened in edit mode, so Delete is offered",
    doc.getElementById("tsTitle").textContent === "Edit trip" &&
    doc.getElementById("tsDel").style.display !== "none");
  doc.getElementById("tsDel").click();
  await drain();
  check("the trip is gone", ev("trips.length") === 0, ev("trips"));
  check("and the calendar event was recorded as dismissed",
    ev("tripsDismissed.includes('ev-1')"), ev("tripsDismissed"));

  d = await ev("scanCalendar()");
  check("THE POINT: rescanning the same event does not bring the trip back",
    d.added === 0 && ev("trips.length") === 0, { d, trips: ev("trips") });
  check("and it is not offered as a candidate to confirm either",
    ev("candidates.length") === 0, ev("candidates"));

  console.log("\n--- 3. editing the city cannot keep the old coordinates ----------");
  ev(`trips=[{id:"trp-1",calId:"ev-9",title:"Client visit",
      start:"2099-09-02",end:"2099-09-05",lat:${CHICAGO.lat},lon:${CHICAGO.lon},
      place:${JSON.stringify(CHICAGO.place)},type:"business",styles:["smart"],
      notifyDays:2,laundryBefore:false,packed:[],auto:true}];
    openTripSheet(trips[0], false, "");`);
  check("the sheet shows the city it was geocoded to",
    doc.getElementById("tsCity").value === "Chicago" &&
    doc.getElementById("tsPlace").textContent === "✓ " + CHICAGO.place);

  const type = (v) => {
    const el = doc.getElementById("tsCity");
    el.value = v; el.dispatchEvent(new w.Event("input", { bubbles: true }));
  };
  type("Osaka");
  check("typing a different city drops the stale geocode",
    ev("tsheet.trip.lat") == null && ev("tsheet.trip.lon") == null, ev("tsheet.trip"));
  check("and the ✓ place line stops claiming the old destination",
    doc.getElementById("tsPlace").style.display === "none",
    doc.getElementById("tsPlace").textContent);

  doc.getElementById("tsSave").click();
  await drain();
  check("THE POINT: Save refuses rather than storing Chicago as \"Osaka\"",
    doc.getElementById("tsErr").textContent === "Find the destination city first.",
    doc.getElementById("tsErr").textContent);
  check("nothing was written to the trip", ev("trips[0].place") === CHICAGO.place &&
    ev("trips[0].lat") === CHICAGO.lat, ev("trips[0]"));

  console.log("\n--- 4. but a trip whose city was NOT edited still saves ----------");
  type("Chicago");
  check("typing the original name back restores its coordinates",
    ev("tsheet.trip.lat") === CHICAGO.lat && ev("tsheet.trip.place") === CHICAGO.place,
    ev("tsheet.trip"));
  check("and the ✓ place line comes back",
    doc.getElementById("tsPlace").style.display === "block");
  ev(`tsheet.trip.notifyDays=5;`);
  doc.getElementById("tsSave").click();
  await drain();
  check("Save goes through — editing only the notice period costs no geocode",
    ev("trips.length") === 1 && ev("trips[0].notifyDays") === 5 &&
    ev("trips[0].place") === CHICAGO.place, ev("trips[0]"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
