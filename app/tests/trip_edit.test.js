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
// Trip dates must be in the future or tsSave refuses them, so they are computed
// rather than written down — a hard-coded date silently expires.
const DAY_ = 86400000;
const iso = (off) => { const d = new Date(Date.now() + off * DAY_);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; };
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
  // Wait for the page to finish initialising. appReady is the real signal;
  // polling for a field load() happens to set early is a guess about one.
  await ev("appReady");
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

  console.log("\n--- trips found under rules we now know were wrong -------------");
  /* v1.15 stopped "PPK" being geocoded to Petropavl, KAZAKHSTAN, but a trip already
     in storage stays on screen for ever — which is why the user still saw
     Kazakhstan after updating (2026-08-23).

     They are FLAGGED, never deleted. `auto` survived an edit in every build before
     1.16, so a trip the user already corrected is indistinguishable from an
     untouched guess, and a corrected destination is not re-derivable. The app does
     not choose; it asks. Raised by the pre-push reviewer. */
  w.localStorage.removeItem("oa.tripsRules");
  ev(`trips=[
    {id:"t1",auto:true,calId:"c1",place:"Petropavl, North Kazakhstan, KZ",title:"Team sync",start:"${iso(20)}",end:"${iso(21)}",packed:[]},
    {id:"t2",place:"Boston, Massachusetts, US",title:"Conference",start:"${iso(30)}",end:"${iso(32)}",packed:[]},
    {id:"t3",auto:true,calId:"c3",place:"Tokyo, JP",title:"Client visit",start:"${iso(40)}",end:"${iso(44)}",packed:[{id:"i1",qty:1}]}];
    tripsDismissed=[];`);
  await ev(`flagTripsFoundUnderOldRules()`);
  check("NOTHING is deleted — an edited trip is not re-derivable",
    ev(`trips.length`) === 3, ev(`trips.map(t=>t.id)`));
  check("the auto-found trip is flagged for review",
    ev(`trips.find(t=>t.id==="t1").needsReview`) === true, ev(`trips[0]`));
  check("a trip the USER made is not questioned",
    !ev(`trips.find(t=>t.id==="t2").needsReview`), ev(`trips[1]`));
  check("nor is one already packed — a packing list is work the user did",
    !ev(`trips.find(t=>t.id==="t3").needsReview`), ev(`trips[2]`));
  check("and the banner explains what happened",
    /PPK/.test(ev(`staleTripNote`)), ev(`staleTripNote`));
  check("the rules stamp is recorded",
    w.localStorage.getItem("oa.tripsRules") === ev(`TRIPS_RULES_VERSION`),
    w.localStorage.getItem("oa.tripsRules"));

  ev(`renderTrips()`);
  check("the flagged trip asks about itself on the card",
    /Found before the location fix/.test(doc.getElementById("tripList").innerHTML));
  check("and offers both answers",
    !!doc.querySelector('[data-keep="t1"]') && !!doc.querySelector('[data-drop="t1"]'));

  console.log("\n--- answering the review question --------------------------------");
  ev(`cancelled=[]; Plugins.OutfitPacking={arm:async()=>true,cancel:async({tripId})=>{cancelled.push(tripId);}};`);
  doc.querySelector('[data-drop="t1"]').click();
  await drain();
  check("Remove takes the trip away", !ev(`trips.some(t=>t.id==="t1")`), ev(`trips.map(t=>t.id)`));
  // cancelTrip keys on the TRIP id, not the calendar event id.
  check("its native reminder is cancelled, so nothing fires for a trip that is gone",
    JSON.stringify(ev(`cancelled`)) === '["t1"]', ev(`cancelled`));
  check("and its calendar event is dismissed, so the next scan cannot re-add it",
    ev(`tripsDismissed.includes("c1")`), ev(`tripsDismissed`));

  // Keep makes the trip the user's, so it is never questioned again.
  w.localStorage.removeItem("oa.tripsRules");
  ev(`trips=[{id:"k1",auto:true,calId:"c5",place:"Osaka, JP",title:"Client",start:"${iso(50)}",end:"${iso(53)}",packed:[]}];`);
  await ev(`flagTripsFoundUnderOldRules()`);
  ev(`renderTrips()`);
  doc.querySelector('[data-keep="k1"]').click();
  await drain();
  const kept = ev(`trips.find(t=>t.id==="k1")`);
  check("Keep leaves the trip in place", !!kept, ev(`trips.map(t=>t.id)`));
  check("and it stops being the app's guess, so no later migration touches it",
    !kept.needsReview && !kept.auto, kept);

  // The stamp is written by the runs above, so this is the second launch: a trip
  // found AFTER the migration must not be questioned.
  ev(`trips=[{id:"t4",auto:true,place:"Nowhere",title:"x",start:"${iso(60)}",end:"${iso(61)}",packed:[]}];`);
  await ev(`flagTripsFoundUnderOldRules()`);
  check("it runs ONCE — a later auto-detected trip is not flagged",
    !ev(`trips[0].needsReview`), ev(`trips[0]`));

  // Nothing to flag must not leave a note claiming something happened.
  w.localStorage.removeItem("oa.tripsRules");
  ev(`trips=[{id:"t5",place:"Osaka, JP",title:"Holiday",start:"${iso(70)}",end:"${iso(74)}",packed:[]}]; staleTripNote="";`);
  await ev(`flagTripsFoundUnderOldRules()`);
  check("a list of hand-made trips produces no note at all",
    ev(`staleTripNote`) === "", ev(`staleTripNote`));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
