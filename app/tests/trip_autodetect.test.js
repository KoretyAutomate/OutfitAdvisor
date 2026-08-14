/**
 * trip_autodetect.test.js — judging trips without asking the user (2026-08-14).
 *
 * The user's objection: confirming every calendar candidate defeats the point of
 * reading the calendar. So the app now asks the DGX what an entry is, geocodes
 * only the CITY that comes back, and decides by distance from home.
 *
 * What matters here is the DECISION TABLE, and especially that every failure
 * degrades to "ask the user" — the old behaviour — rather than losing a trip or
 * inventing one. A wrong "skip" is invisible: the user simply never hears about a
 * trip they have, which is worse than being asked.
 *
 * Run: NODE_PATH=<...>/node_modules node tests/trip_autodetect.test.js
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

// Princeton NJ, rounded exactly as the app stores it (~11 km grid).
const HOME = '{label:"Princeton, New Jersey, 08540",postal:"08540",lat:40.4,lon:-74.7}';

/** Fake the two network calls triageCandidate makes. */
function stub({ triage, cities, triageFails }) {
  ev(`
    globalThis.__geocoded = [];
    fetch = async (url, opts) => {
      if (String(url).includes("/triage")) {
        if (${!!triageFails}) throw new Error("unreachable");
        return { ok: true, json: async () => (${JSON.stringify(triage)}) };
      }
      throw new Error("unexpected fetch: " + url);
    };
    geocode = async (city) => {
      globalThis.__geocoded.push(city);
      const table = ${JSON.stringify(cities)};
      if (!table[city]) throw new Error('Couldn\\'t find "' + city + '".');
      return table[city];
    };
  `);
}

const CHICAGO = { lat: 41.88, lon: -87.63, place: "Chicago, Illinois, US" };
const NEWARK = { lat: 40.74, lon: -74.17, place: "Newark, New Jersey, US" };
const CAND = (over = {}) => JSON.stringify(Object.assign(
  { calId: "e1", title: "Client visit", hint: "Marriott Downtown Chicago",
    nights: 3, start: "2026-09-02", end: "2026-09-05" }, over));

(async () => {
  for (let i = 0; i < 20 && !ev("state.baseUrl"); i++) await drain();
  await new Promise(r => setTimeout(r, 30));

  console.log("\n--- 1. the decision table ---------------------------------------");
  ev(`home = ${HOME};`);

  stub({ triage: { isTrip: true, city: "Chicago", type: "business", confidence: .95, reason: "hotel" },
         cities: { Chicago: CHICAGO } });
  let v = await ev(`triageCandidate(${CAND()})`);
  check("far + overnight + travel -> trip", v.decision === "trip", v);
  check("the trip carries the resolved city, not the hotel string",
    v.city === "Chicago" && v.place === "Chicago, Illinois, US", v);
  check("and its distance", v.km === 1099 || Math.abs(v.km - 1099) < 30, v.km);
  check("ONLY the city was geocoded — never the raw location",
    JSON.stringify(ev("globalThis.__geocoded")) === '["Chicago"]', ev("globalThis.__geocoded"));

  stub({ triage: { isTrip: false, city: null, type: "vacation", confidence: .95, reason: "local dentist" },
         cities: {} });
  v = await ev(`triageCandidate(${CAND({ title: "Dentist", hint: "Princeton Family Dental", nights: 0 })})`);
  check("not travel -> skip", v.decision === "skip", v);
  check("nothing is geocoded when it isn't travel",
    JSON.stringify(ev("globalThis.__geocoded")) === "[]", ev("globalThis.__geocoded"));

  stub({ triage: { isTrip: true, city: "Newark", type: "business", confidence: .9, reason: "office" },
         cities: { Newark: NEWARK } });
  v = await ev(`triageCandidate(${CAND({ hint: "Newark office" })})`);
  check("travel but under 100 km -> skip", v.decision === "skip", v);
  check("and it says how far", /km from home/.test(v.why), v.why);

  stub({ triage: { isTrip: true, city: "Chicago", type: "business", confidence: .95, reason: "x" },
         cities: { Chicago: CHICAGO } });
  v = await ev(`triageCandidate(${CAND({ nights: 0 })})`);
  check("far but no overnight -> skip", v.decision === "skip", v);

  console.log("\n--- 2. every failure degrades to ASKING, never to guessing --------");
  ev("home = null;");
  stub({ triage: { isTrip: true, city: "Chicago", type: "business", confidence: 1, reason: "x" },
         cities: { Chicago: CHICAGO } });
  v = await ev(`triageCandidate(${CAND()})`);
  check("no home area set -> ask (cannot measure distance)", v.decision === "ask", v);

  ev(`home = ${HOME};`);
  stub({ triage: {}, cities: {}, triageFails: true });
  v = await ev(`triageCandidate(${CAND()})`);
  check("advisor unreachable -> ask, not skip", v.decision === "ask", v);

  stub({ triage: { isTrip: true, city: null, type: "vacation", confidence: .4, reason: "unclear" },
         cities: {} });
  v = await ev(`triageCandidate(${CAND()})`);
  check("travel but no city determined -> ask", v.decision === "ask", v);

  stub({ triage: { isTrip: true, city: "Narnia", type: "vacation", confidence: .9, reason: "x" },
         cities: { Chicago: CHICAGO } });
  v = await ev(`triageCandidate(${CAND()})`);
  check("city that will not geocode -> ask", v.decision === "ask", v);
  check("and it names the city that failed", /Narnia/.test(v.why), v.why);

  console.log("\n--- 3. home is stored coarsely ------------------------------------");
  check("coordinates round to ~11 km, far below the 100 km threshold",
    ev("roundCoarse(40.3573)") === 40.4 && ev("roundCoarse(-74.6672)") === -74.7);
  check("the threshold is the agreed 100 km", ev("TRIP_MIN_KM") === 100);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
