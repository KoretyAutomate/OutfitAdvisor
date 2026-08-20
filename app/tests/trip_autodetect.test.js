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
 * Run: npm test   (or: node tests/trip_autodetect.test.js — jsdom is a devDependency since 2026-08-20)
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
  // stub() replaces geocode wholesale, so keep the real one to test on its own.
  ev("globalThis.__realGeocode = geocode;");

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

  console.log("\n--- 4. the Kazakhstan gates (2026-08-20) -------------------------");
  /* The user saw automatically-added trips to cities that appear nowhere in their
     calendar — "Petropavl, North Kazakhstan, KZ". Three things had to line up:
     the advisor was allowed to be unsure, the city string was never checked, and
     a fuzzy geocode's answer was never compared with what was asked. Each one is
     now a gate, and each gate degrades to ASK, never to skip. */
  ev(`home = ${HOME};`);

  check("geoNameMatches: the same city matches", ev(`geoNameMatches("Chicago","Chicago")`));
  check("geoNameMatches: case and accents are folded",
    ev(`geoNameMatches("krakow","Kraków")`) && ev(`geoNameMatches("SÃO PAULO","Sao Paulo")`));
  check("geoNameMatches: a longer form of the same name matches, both ways round",
    ev(`geoNameMatches("New York City","New York")`) &&
    ev(`geoNameMatches("Frankfurt","Frankfurt am Main")`));
  check("geoNameMatches: a comma-tail is ignored on both sides",
    ev(`geoNameMatches("Chicago","Chicago, Illinois, US")`));
  check("geoNameMatches: a different place does NOT match",
    !ev(`geoNameMatches("Petro","Petropavl")`) &&
    !ev(`geoNameMatches("Newark","Petropavl, North Kazakhstan, KZ")`));
  check("geoNameMatches: a fuzzy expansion INSIDE a word is not a match",
    !ev(`geoNameMatches("Petro","Petropavl")`) &&
    !ev(`geoNameMatches("Petropavl","Petro")`));
  check("geoNameMatches: a single short word is an initial, not a name",
    !ev(`geoNameMatches("San","San Francisco")`));
  check("geoNameMatches: nothing matches an empty name",
    !ev(`geoNameMatches("","Chicago")`) && !ev(`geoNameMatches("Chicago","")`));

  stub({ triage: { isTrip: true, city: "Chicago", type: "business", confidence: .4, reason: "maybe" },
         cities: { Chicago: CHICAGO } });
  v = await ev(`triageCandidate(${CAND()})`);
  check("an unsure advisor -> ask, never an auto-added trip", v.decision === "ask", v);
  check("and it says how unsure", /%/.test(v.why), v.why);
  check("nothing is geocoded once the confidence gate has closed",
    JSON.stringify(ev("globalThis.__geocoded")) === "[]", ev("globalThis.__geocoded"));

  stub({ triage: { isTrip: true, city: "Chicago", type: "business", confidence: .6, reason: "hotel" },
         cities: { Chicago: CHICAGO } });
  v = await ev(`triageCandidate(${CAND()})`);
  check("exactly at the floor still counts as sure", v.decision === "trip", v);

  stub({ triage: { isTrip: true, city: "2026", type: "vacation", confidence: .9, reason: "x" },
         cities: {} });
  v = await ev(`triageCandidate(${CAND()})`);
  check("a city name with no letters -> ask", v.decision === "ask", v);
  check("and it never reaches the public geocoder",
    JSON.stringify(ev("globalThis.__geocoded")) === "[]", ev("globalThis.__geocoded"));

  // The bug itself: the geocoder answers a place nobody asked about, and because
  // that place is far away the distance test PASSES. Wronger => more certain.
  stub({ triage: { isTrip: true, city: "Petro", type: "vacation", confidence: .9, reason: "x" },
         cities: { Petro: { lat: 54.87, lon: 69.15, place: "Petropavl, North Kazakhstan, KZ" } } });
  v = await ev(`triageCandidate(${CAND()})`);
  check("a geocode that answers a DIFFERENT city -> ask, not a trip to Kazakhstan",
    v.decision === "ask", v);
  check("and it shows both names so the mismatch is visible",
    /Petro/.test(v.why) && /Petropavl/.test(v.why), v.why);

  console.log("\n--- 4b. the qualifier is part of the name (2026-08-20) -----------");
  /* The model is asked for a bare city and does not always give one: it writes
     "Cambridge, UK" or "Springfield, IL". Comparing only the token before the
     comma re-opens the wrong-destination hole the section above closes — the
     distance test passes for the wrong Cambridge exactly as it did for Petropavl,
     and nobody is looking. */
  const OM = (place, regions) => JSON.stringify({ place, regions });

  check("geoPlaceMatches: an unqualified name still matches, as before",
    ev(`geoPlaceMatches("Chicago","Chicago, Illinois, US")`) &&
    ev(`geoPlaceMatches("Frankfurt",${OM("Frankfurt am Main, Hesse, DE", ["Hesse", "Germany", "DE"])})`));
  check("geoPlaceMatches: the qualifier must describe the place that came back",
    !ev(`geoPlaceMatches("Cambridge, UK",${OM("Cambridge, Massachusetts, US", ["Massachusetts", "United States", "US"])})`),
    "Cambridge, UK accepted Cambridge, Massachusetts");
  check("geoPlaceMatches: and the RIGHT region is still accepted",
    ev(`geoPlaceMatches("Cambridge, UK",${OM("Cambridge, England, GB", ["England", "United Kingdom", "GB"])})`));
  check("geoPlaceMatches: a country in full or as a code both land",
    ev(`geoPlaceMatches("Tokyo, Japan",${OM("Tokyo, Tokyo, JP", ["Tokyo", "Japan", "JP"])})`) &&
    ev(`geoPlaceMatches("Tokyo, JP",${OM("Tokyo, Tokyo, JP", ["Tokyo", "Japan", "JP"])})`));
  check("geoPlaceMatches: two same-named cities are told apart by their state",
    ev(`geoPlaceMatches("Springfield, Illinois",${OM("Springfield, Illinois, US", ["Illinois", "United States", "US"])})`) &&
    !ev(`geoPlaceMatches("Springfield, Illinois",${OM("Springfield, Missouri, US", ["Missouri", "United States", "US"])})`));
  check("geoPlaceMatches: a qualifier nothing can confirm fails CLOSED — an ambiguous "
    + "subdivision code is never guessed at",
    !ev(`geoPlaceMatches("Springfield, IL",${OM("Springfield, Illinois, US", ["Illinois", "United States", "US"])})`));
  check("geoPlaceMatches: a place with no regions at all cannot satisfy a qualifier",
    !ev(`geoPlaceMatches("Cambridge, UK","Cambridge")`));

  // End to end: the same failure as Petropavl, dressed as a plausible answer.
  stub({ triage: { isTrip: true, city: "Cambridge, UK", type: "business", confidence: .95, reason: "conference" },
         cities: { "Cambridge, UK": { lat: 42.37, lon: -71.11, place: "Cambridge, Massachusetts, US",
                                      regions: ["Massachusetts", "United States", "US"] } } });
  v = await ev(`triageCandidate(${CAND({ hint: "Trinity College Cambridge" })})`);
  check("a qualified city answered with the wrong country -> ask, not a trip to Massachusetts",
    v.decision === "ask", v);

  stub({ triage: { isTrip: true, city: "Cambridge, UK", type: "business", confidence: .95, reason: "conference" },
         cities: { "Cambridge, UK": { lat: 52.2, lon: 0.12, place: "Cambridge, England, GB",
                                      regions: ["England", "United Kingdom", "GB"] } } });
  v = await ev(`triageCandidate(${CAND({ hint: "Trinity College Cambridge" })})`);
  check("and the right Cambridge is still added on its own", v.decision === "trip", v);

  console.log("\n--- 4c. the automatic path demands the SAME name (2026-08-20) ----");
  /* The loose test lets a name grow by whole words, so that "Frankfurt" can be
     answered with "Frankfurt am Main". That is right for a typed city — a human
     reads the answer — and wrong for a trip the app adds by itself, because
     growing by whole words is ALSO how two different cities are spelled:
     Frankfurt (Oder) is 500 km from Frankfurt am Main, and York New Salem is not
     York. Asked for a bare "Frankfurt", nothing in the string says which, so the
     automatic path asks instead of guessing. */

  check("geoNameExact: the same name matches, accents and case folded",
    ev(`geoNameExact("Chicago","Chicago")`) && ev(`geoNameExact("krakow","Kraków")`));
  check("geoNameExact: a comma-tail is still not part of the head",
    ev(`geoNameExact("Chicago","Chicago, Illinois, US")`));
  check("geoNameExact: a name that merely EXTENDS is not the same name",
    !ev(`geoNameExact("Frankfurt","Frankfurt am Main")`) &&
    !ev(`geoNameExact("Frankfurt","Frankfurt (Oder)")`) &&
    !ev(`geoNameExact("York","York New Salem")`) &&
    !ev(`geoNameExact("Newark","Newark on Trent")`));
  check("geoNameExact: but a listed alias is two spellings of ONE place",
    ev(`geoNameExact("New York City","New York")`) &&
    ev(`geoNameExact("NYC","New York")`));
  check("geoNameExact: nothing matches an empty name",
    !ev(`geoNameExact("","Chicago")`) && !ev(`geoNameExact("Chicago","")`));
  check("the loose test is UNCHANGED — the typed-city path still re-ranks by prefix",
    ev(`geoNameMatches("Frankfurt","Frankfurt am Main")`) &&
    ev(`geoNameMatches("York","York New Salem")`));

  check("geoPlaceExact: the qualifier rule still applies on top of the strict head",
    ev(`geoPlaceExact("Cambridge, UK",${OM("Cambridge, England, GB", ["England", "United Kingdom", "GB"])})`) &&
    !ev(`geoPlaceExact("Cambridge, UK",${OM("Cambridge, Massachusetts, US", ["Massachusetts", "United States", "US"])})`));
  check("geoPlaceExact: a prefix hit the loose test accepts is refused here",
    ev(`geoPlaceMatches("Frankfurt",${OM("Frankfurt (Oder), Brandenburg, DE", ["Brandenburg", "Germany", "DE"])})`) &&
    !ev(`geoPlaceExact("Frankfurt",${OM("Frankfurt (Oder), Brandenburg, DE", ["Brandenburg", "Germany", "DE"])})`));

  // End to end: the wrong Frankfurt, 500 km from the right one, with a name that
  // reads like a match. Nobody is looking, so it must not become a trip.
  stub({ triage: { isTrip: true, city: "Frankfurt", type: "business", confidence: .95, reason: "conference" },
         cities: { Frankfurt: { lat: 52.35, lon: 14.55, place: "Frankfurt (Oder), Brandenburg, DE",
                                regions: ["Brandenburg", "Germany", "DE"] } } });
  v = await ev(`triageCandidate(${CAND({ hint: "Messe Frankfurt" })})`);
  check("a city answered with a LONGER name -> ask, not a trip to the wrong Frankfurt",
    v.decision === "ask", v);
  check("and it shows both names so the mismatch is visible",
    /Frankfurt \(Oder\)/.test(v.why), v.why);

  stub({ triage: { isTrip: true, city: "Frankfurt", type: "business", confidence: .95, reason: "conference" },
         cities: { Frankfurt: { lat: 50.11, lon: 8.68, place: "Frankfurt, Hesse, DE",
                                regions: ["Hesse", "Germany", "DE"] } } });
  v = await ev(`triageCandidate(${CAND({ hint: "Messe Frankfurt" })})`);
  check("and the Frankfurt that IS named Frankfurt is still added on its own",
    v.decision === "trip", v);

  console.log("\n--- 5. geocode() steps over a fuzzy top hit -----------------------");
  /* Open-Meteo ranks something first for almost any string and gives no score, so
     count=1 left no way to tell a direct hit from a desperate one. */
  const omStub = (results) => ev(`
    geocode = globalThis.__realGeocode;
    globalThis.__url = "";
    fetch = async (url) => { globalThis.__url = String(url);
      return { ok: true, json: async () => ({ results: ${JSON.stringify(results)} }) }; };
  `);

  omStub([
    { name: "Petropavl", admin1: "North Kazakhstan", country_code: "KZ", latitude: 54.87, longitude: 69.15 },
    { name: "Chicago", admin1: "Illinois", country_code: "US", latitude: 41.88, longitude: -87.63 },
  ]);
  let g = await ev(`geocode("Chicago")`);
  check("the first result that IS the city asked for wins",
    g.place === "Chicago, Illinois, US", g);
  check("and more than one candidate is requested", /count=5/.test(ev("globalThis.__url")),
    ev("globalThis.__url"));

  omStub([{ name: "Petropavl", admin1: "North Kazakhstan", country_code: "KZ", latitude: 54.87, longitude: 69.15 }]);
  g = await ev(`geocode("Petro")`);
  check("with no match at all the API's own answer is still returned — the CALLER decides",
    g.place === "Petropavl, North Kazakhstan, KZ", g);

  omStub([
    { name: "Springfield", admin1: "Missouri", country: "United States", country_code: "US", latitude: 37.21, longitude: -93.29 },
    { name: "Springfield", admin1: "Illinois", country: "United States", country_code: "US", latitude: 39.80, longitude: -89.64 },
  ]);
  g = await ev(`geocode("Springfield, Illinois")`);
  check("a qualified query picks the Springfield that was asked for, not the biggest",
    g.place === "Springfield, Illinois, US", g);
  check("and the comma-tail is stripped from the QUERY — Open-Meteo matches a name, not a name+state",
    /name=Springfield&/.test(ev("globalThis.__url")), ev("globalThis.__url"));
  check("the geocoder's own region fields come back for the caller to test",
    JSON.stringify(g.regions) === '["Illinois","United States","US"]', g.regions);

  omStub([
    { name: "Frankfurt (Oder)", admin1: "Brandenburg", country: "Germany", country_code: "DE", latitude: 52.35, longitude: 14.55 },
    { name: "Frankfurt", admin1: "Hesse", country: "Germany", country_code: "DE", latitude: 50.11, longitude: 8.68 },
  ]);
  g = await ev(`geocode("Frankfurt")`);
  check("a result NAMED the city beats one that only extends it, whatever the API's order",
    g.place === "Frankfurt, Hesse, DE", g);

  omStub([
    { name: "Petropavl", admin1: "North Kazakhstan", country: "Kazakhstan", country_code: "KZ", latitude: 54.87, longitude: 69.15 },
    { name: "Frankfurt am Main", admin1: "Hesse", country: "Germany", country_code: "DE", latitude: 50.11, longitude: 8.68 },
  ]);
  g = await ev(`geocode("Frankfurt")`);
  check("with no exact name at all the loose match is still preferred to the API's top answer",
    g.place === "Frankfurt am Main, Hesse, DE", g);

  omStub([]);
  let threw = false;
  try { await ev(`geocode("Narnia")`); } catch (e) { threw = true; }
  check("no results at all still throws", threw);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
