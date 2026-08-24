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
  // Wait for the page to finish initialising. appReady is the real signal;
  // polling for a field load() happens to set early is a guess about one.
  await ev("appReady");
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
  check("and the reason names the city ASKED for, never the one that came back",
    /Petro"/.test(v.why) && !/Petropavl|Kazakh/i.test(v.why), v.why);

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
  check("and the reason does not repeat the wrong Frankfurt back at the user",
    /Frankfurt/.test(v.why) && !/Oder/.test(v.why), v.why);

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
  check("and a WIDE candidate list is requested — the right answer is often 6th or 8th",
    /count=20/.test(ev("globalThis.__url")), ev("globalThis.__url"));

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

  console.log("\n--- 6. codes are not cities (PPK / LVL, user 2026-08-23) ---------");
  /* Open-Meteo resolves IATA codes. Verified against the live API on 2026-08-23:
       PPK -> Petropavl, KAZAKHSTAN        (the user's office on Princeton Pike, NJ)
       LVL -> Lawrenceville, VIRGINIA      (the user's Lawrenceville is in NJ, 9 km)
     Both answer with total confidence, and the distance test then CONFIRMS the
     trip precisely BECAUSE the answer is far away — the wronger the hit, the more
     certainly it becomes a trip to Kazakhstan. */
  /* The gate is the strict NAME test that was already here: PPK comes back named
     Petropavl, and a place that is not the place we asked about has not been
     placed. No shape rule — see the note on geoUnplaceableShort for why every
     shape rule tried here was wrong more often than right. */
  ev(`home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672};`);
  ev(`
    fetch = async (url) => {
      const u = String(url);
      if (u.indexOf("/triage") >= 0) return { ok:true, json: async () => (
        {isTrip:true, city:"PPK", type:"business", confidence:0.9, reason:"offsite"}) };
      return { ok:true, json: async () => ({ results: [
        { name:"Petropavl", admin1:"North Kazakhstan", country:"Kazakhstan", country_code:"KZ",
          latitude:54.87, longitude:69.15 }] }) };
    };`);
  let vc = await ev(`triageCandidate({title:"Team sync",hint:"PPK",nights:1,
                     start:"2026-09-02",end:"2026-09-03"})`);
  check("PPK is ASKED about, never turned into a trip to Kazakhstan",
    vc.decision === "ask", vc);
  check("and the reason does not name the country nobody mentioned",
    !/kazakh|petropavl/i.test(vc.why || ""), vc);

  // LVL is the nastier one: the name that comes back IS the name asked about, so
  // only the region tells Virginia from New Jersey.
  ev(`
    fetch = async (url) => {
      const u = String(url);
      if (u.indexOf("/triage") >= 0) return { ok:true, json: async () => (
        {isTrip:true, city:"Lawrenceville", type:"business", confidence:0.9, reason:"offsite"}) };
      return { ok:true, json: async () => ({ results: [
        { name:"Lawrenceville", admin1:"Virginia",   country:"United States", country_code:"US", latitude:36.758, longitude:-77.847 },
        { name:"Lawrenceville", admin1:"New Jersey", country:"United States", country_code:"US", latitude:40.297, longitude:-74.729 }] }) };
    };`);
  vc = await ev(`triageCandidate({title:"Team sync",hint:"LVL",nights:1,
                 start:"2026-09-02",end:"2026-09-03"})`);
  check("two far-apart Lawrencevilles are asked about, not guessed",
    vc.decision === "ask", vc);

  console.log("\n--- 7. of two same-named towns, the near one is meant -----------");
  /* Open-Meteo ranks by population, so the user's OWN town loses to bigger
     namesakes. Live on 2026-08-23, "Princeton" put New Jersey 6th and
     "Lawrenceville" put New Jersey 8th — at count=5 neither was reachable. */
  const LAWRENCEVILLES = [
    { name: "Lawrenceville", admin1: "Georgia",    country: "United States", country_code: "US", latitude: 33.956, longitude: -83.988 },
    { name: "Lawrenceville", admin1: "Illinois",   country: "United States", country_code: "US", latitude: 38.729, longitude: -87.682 },
    { name: "Lawrenceville", admin1: "Virginia",   country: "United States", country_code: "US", latitude: 36.758, longitude: -77.847 },
    { name: "Lawrenceville", admin1: "New Jersey", country: "United States", country_code: "US", latitude: 40.297, longitude: -74.729 },
  ];
  omStub(LAWRENCEVILLES);
  ev(`home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672};`);
  let gl = await ev(`geocode("Lawrenceville")`);
  check("the Lawrenceville 9 km away wins over the one 486 km away",
    gl.place === "Lawrenceville, New Jersey, US", gl);

  // The tie-break must not override the NAME test, only settle it.
  omStub([
    { name: "Pierceton", admin1: "New Jersey", country: "United States", country_code: "US", latitude: 40.30, longitude: -74.70 },
    { name: "Princeton", admin1: "Indiana",    country: "United States", country_code: "US", latitude: 38.355, longitude: -87.568 },
  ]);
  gl = await ev(`geocode("Princeton")`);
  check("a nearer town with the WRONG name still loses to the right name far away",
    gl.place === "Princeton, Indiana, US", gl);

  // An explicit qualifier still decides, whatever is nearest.
  omStub(LAWRENCEVILLES);
  gl = await ev(`geocode("Lawrenceville, Georgia")`);
  check("naming the state overrides the nearest-home tie-break",
    gl.place === "Lawrenceville, Georgia, US", gl);

  // With no home there is nothing to measure from; the API's order must survive.
  ev(`home = null;`);
  omStub(LAWRENCEVILLES);
  gl = await ev(`geocode("Lawrenceville")`);
  check("with no home set the geocoder's own order is left alone",
    gl.place === "Lawrenceville, Georgia, US", gl);

  console.log("\n--- 8. a bare city near home is not a trip ----------------------");
  /* The whole point of the tie-break: the model answering a Princeton-NJ meeting
     with a bare "Princeton" used to geocode to Indiana, 1,130 km away, and the
     distance test turned that into a trip nobody was taking. */
  ev(`home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672};`);
  ev(`
    fetch = async (url) => {
      const u = String(url);
      if (u.indexOf("/triage") >= 0) return { ok:true, json: async () => (
        {isTrip:true, city:"Princeton", type:"business", confidence:0.9, reason:"offsite"}) };
      return { ok:true, json: async () => ({ results: [
        { name:"Princeton", admin1:"Indiana",    country:"United States", country_code:"US", latitude:38.355, longitude:-87.568 },
        { name:"Princeton", admin1:"New Jersey", country:"United States", country_code:"US", latitude:40.348, longitude:-74.659 }] }) };
    };`);
  vc = await ev(`triageCandidate({title:"Offsite",hint:"",nights:1,
                 start:"2026-09-02",end:"2026-09-03"})`);
  /* Not "trip" — that was the invented-Indiana bug. But not "skip" either: a
     bare name shared by two far-apart places says nothing about which is meant,
     and quietly choosing the near one CANCELS a genuine trip to the far one.
     Raised by the pre-push reviewer, 2026-08-23; it was right. */
  check("an ambiguous bare city name is ASKED about, not decided either way",
    vc.decision === "ask", vc);
  check("and the reason names the ambiguity", /names 2 different places/.test(vc.why || ""), vc);

  // Unambiguous stays automatic — the tie-break only fires where there IS a tie.
  ev(`
    fetch = async (url) => {
      const u = String(url);
      if (u.indexOf("/triage") >= 0) return { ok:true, json: async () => (
        {isTrip:true, city:"Reykjavik", type:"vacation", confidence:0.9, reason:"holiday"}) };
      return { ok:true, json: async () => ({ results: [
        { name:"Reykjavik", admin1:"Capital", country:"Iceland", country_code:"IS", latitude:64.146, longitude:-21.94 }] }) };
    };`);
  vc = await ev(`triageCandidate({title:"Holiday",hint:"",nights:5,
                 start:"2026-09-02",end:"2026-09-07"})`);
  check("a city with only ONE claimant is still added automatically",
    vc.decision === "trip", vc);

  // Two namesakes CLOSE together are not an ambiguity worth a tap: whichever is
  // meant, the trip/skip answer is the same.
  ev(`
    fetch = async (url) => {
      const u = String(url);
      if (u.indexOf("/triage") >= 0) return { ok:true, json: async () => (
        {isTrip:true, city:"Springfield", type:"business", confidence:0.9, reason:"offsite"}) };
      return { ok:true, json: async () => ({ results: [
        { name:"Springfield", admin1:"Illinois", country:"United States", country_code:"US", latitude:39.80, longitude:-89.64 },
        { name:"Springfield", admin1:"Illinois", country:"United States", country_code:"US", latitude:39.85, longitude:-89.70 }] }) };
    };`);
  vc = await ev(`triageCandidate({title:"Offsite",hint:"",nights:1,
                 start:"2026-09-02",end:"2026-09-03"})`);
  check("namesakes in the same place do not trigger a needless question",
    vc.decision === "trip", vc);

  console.log("\n--- 9. lowercase codes, without refusing Rome ------------------");
  /* The reviewer flagged that the shape test only matches uppercase, and it was
     right that "ppk" got through. Its suggested fix — lowercase the input, or make
     the regex case-insensitive — would refuse Rome, Oslo, Nice, Lyon, Bath, York,
     Kobe, Pisa, Graz, Cork, Riga, Bonn, Linz and Gent, all real cities of four
     letters or fewer. So the ANSWER is tested instead of the query: a short real
     name comes back bearing that name, a code comes back bearing another. */
  const asRome = [{ lat: 41.89, lon: 12.48, place: "Rome, Lazio, Italy" }];
  const asPetro = [{ lat: 54.87, lon: 69.15, place: "Petropavl, North Kazakhstan, Kazakhstan" }];
  check("'ppk' answered with Petropavl is unplaceable",
    ev(`geoUnplaceableShort("ppk",${JSON.stringify(asPetro)})`));
  check("'PPK' likewise, whatever the case",
    ev(`geoUnplaceableShort("PPK",${JSON.stringify(asPetro)})`));
  check("'rome' answered with Rome is a real short city, not a code",
    !ev(`geoUnplaceableShort("rome",${JSON.stringify(asRome)})`));
  for (const city of ["oslo", "nice", "lyon", "bath", "york", "kobe", "pisa", "graz", "cork", "riga"]) {
    const answer = [{ lat: 0, lon: 0, place: `${city[0].toUpperCase()}${city.slice(1)}, Somewhere, XX` }];
    check(`'${city}' is not refused as a code`,
      !ev(`geoUnplaceableShort(${JSON.stringify(city)},${JSON.stringify(answer)})`));
  }
  check("a LONG query that matches nothing is not called a code — it is a typo",
    !ev(`geoUnplaceableShort("Pettropavvl",${JSON.stringify(asPetro)})`));

  /* The case the reviewer caught: a shape rule refuses a PASTED name too. Calendar
     text and copied addresses arrive upper-cased all the time, and "ROME" is a
     city however it is typed. Every short city is checked in BOTH cases. */
  for (const city of ["rome", "oslo", "nice", "lyon", "bath", "york", "kobe",
                      "pisa", "graz", "cork", "riga", "bonn", "linz", "gent"]) {
    const proper = city[0].toUpperCase() + city.slice(1);
    const answer = [{ lat: 0, lon: 0, place: `${proper}, Somewhere, XX` }];
    check(`'${city.toUpperCase()}' pasted in caps still geocodes`,
      !ev(`geoUnplaceableShort(${JSON.stringify(city.toUpperCase())},${JSON.stringify(answer)})`));
    check(`'${proper}' typed normally still geocodes`,
      !ev(`geoUnplaceableShort(${JSON.stringify(proper)},${JSON.stringify(answer)})`));
  }
  check("'LVL' answered with Lawrenceville, Virginia is refused — nothing is named LVL",
    ev(`geoUnplaceableShort("LVL",[{lat:0,lon:0,place:"Lawrenceville, Virginia, United States"}])`));

  console.log("\n--- 10. the picker honours what the user typed -------------------");
  /* geocodeMany strips the qualifier from the QUERY, because Open-Meteo matches a
     name and "Lawrenceville, Georgia" as a query matches nothing. So the qualifier
     has to be applied to the ANSWERS instead — otherwise stripping it silently
     throws away the one thing the user said. Raised by the pre-push reviewer. */
  const LV = [
    { name: "Lawrenceville", admin1: "Georgia",    country: "United States", country_code: "US", latitude: 33.956, longitude: -83.988 },
    { name: "Lawrenceville", admin1: "New Jersey", country: "United States", country_code: "US", latitude: 40.297, longitude: -74.729 },
    { name: "Lawrenceville", admin1: "Virginia",   country: "United States", country_code: "US", latitude: 36.758, longitude: -77.847 },
  ];
  ev(`home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672};`);
  omStub(LV);
  let mm = await ev(`geocodeMany("Lawrenceville, Georgia")`);
  check("naming Georgia puts Georgia first, though New Jersey is 1000 km nearer",
    /Georgia/.test(mm[0].place), mm.map(x => x.place));
  check("the others are still offered, never dropped", mm.length === 3, mm.length);

  omStub(LV);
  mm = await ev(`geocodeMany("Lawrenceville")`);
  check("with NO qualifier the nearest wins", /New Jersey/.test(mm[0].place),
    mm.map(x => x.place));
  check("and each answer carries its distance from home", mm[0].km === 9, mm[0].km);

  omStub(LV);
  mm = await ev(`geocodeMany("Lawrenceville, Atlantis")`);
  check("a qualifier nothing matches still leaves every answer to choose from",
    mm.length === 3, mm.length);

  console.log("\n--- 10a. an ISO code qualifier matches in the picker too --------");
  /* The picker's own objects must carry the geocoder's region FIELDS, not just the
     display string: that string ends in the full country name, so "Osaka, JP" and
     "Paris, FR" would match nothing and rank a correctly qualified destination
     below the misses. Raised by the pre-push reviewer, 2026-08-23. */
  omStub([
    { name: "Paris", admin1: "Texas",       country: "United States", country_code: "US", latitude: 33.66, longitude: -95.55 },
    { name: "Paris", admin1: "Ile-de-France", country: "France",      country_code: "FR", latitude: 48.85, longitude: 2.35 },
  ]);
  ev(`home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672};`);
  mm = await ev(`geocodeMany("Paris, FR")`);
  check("a two-letter country code puts France first, though Texas is far nearer",
    /France/.test(mm[0].place), mm.map(x => x.place));
  check("the picker's answers carry the geocoder's own region fields",
    Array.isArray(mm[0].regions) && mm[0].regions.includes("FR"), mm[0].regions);

  omStub([
    { name: "Paris", admin1: "Texas",       country: "United States", country_code: "US", latitude: 33.66, longitude: -95.55 },
    { name: "Paris", admin1: "Ile-de-France", country: "France",      country_code: "FR", latitude: 48.85, longitude: 2.35 },
  ]);
  mm = await ev(`geocodeMany("Paris, France")`);
  check("and the long country name still works", /France/.test(mm[0].place),
    mm.map(x => x.place));

  console.log("\n--- 10b. same name, different town, is not a duplicate ----------");
  /* Open-Meteo really does return three separate Lawrencevilles in Pennsylvania:
     143, 275 and 448 km from this user (live, 2026-08-23). A label-only dedupe key
     collapsed them to whichever came first, hiding the nearest — and could leave a
     single result that findCity() then auto-selects. Raised by the pre-push
     reviewer. */
  const PA = [
    { name: "Lawrenceville", admin1: "Pennsylvania", country: "United States", country_code: "US", latitude: 41.998, longitude: -77.126 },
    { name: "Lawrenceville", admin1: "Pennsylvania", country: "United States", country_code: "US", latitude: 40.463, longitude: -79.965 },
    { name: "Lawrenceville", admin1: "Pennsylvania", country: "United States", country_code: "US", latitude: 40.983, longitude: -75.181 },
  ];
  omStub(PA);
  mm = await ev(`geocodeMany("Lawrenceville")`);
  check("three distinct Pennsylvania towns all survive", mm.length === 3,
    mm.map(x => `${x.place} ${x.km}km`));
  check("and the nearest of them is offered first",
    mm[0].km <= mm[1].km && mm[1].km <= mm[2].km, mm.map(x => x.km));

  // The genuine duplicate — the same record twice at a slightly different centre —
  // is still collapsed, which is what the dedupe is for.
  omStub([
    { name: "Springfield", admin1: "Illinois", country: "United States", country_code: "US", latitude: 39.800, longitude: -89.640 },
    { name: "Springfield", admin1: "Illinois", country: "United States", country_code: "US", latitude: 39.802, longitude: -89.641 },
  ]);
  mm = await ev(`geocodeMany("Springfield")`);
  check("but one town listed twice at almost the same spot collapses to one",
    mm.length === 1, mm.map(x => x.place));

  console.log("\n--- 11. a lone answer is not auto-committed over a qualifier ----");
  /* "Osaka, Texas" returns exactly one result — Osaka, JAPAN. Picking it silently
     overrules the user's own qualifier with a shrug. */
  const openSheet = () => ev(`
    tsheet = {trip:{id:"t1",start:"2026-09-01",end:"2026-09-03",styles:["casual"]},
              isNew:true, matches:[], geo:null};
    document.getElementById("tsPlace").style.display = "none";
    document.getElementById("tsErr").textContent = "";`);

  openSheet();
  ev(`document.getElementById("tsCity").value = "Osaka, Texas";`);
  omStub([{ name: "Osaka", admin1: "Osaka", country: "Japan", country_code: "JP", latitude: 34.69, longitude: 135.50 }]);
  await ev(`findCity()`);
  check("a sole answer failing the qualifier is NOT auto-picked",
    ev(`tsheet.trip.lat`) == null, ev(`tsheet.trip.place`));
  check("it is offered for the user to confirm instead",
    /data-pick="0"/.test(ev(`document.getElementById("tsMatches").innerHTML`)));
  check("and the mismatch is stated plainly",
    /Nothing matched "Texas"/.test(ev(`document.getElementById("tsErr").textContent`)),
    ev(`document.getElementById("tsErr").textContent`));

  openSheet();
  ev(`document.getElementById("tsCity").value = "Osaka, Japan";`);
  omStub([{ name: "Osaka", admin1: "Osaka", country: "Japan", country_code: "JP", latitude: 34.69, longitude: 135.50 }]);
  await ev(`findCity()`);
  check("a sole answer that DOES match is still auto-picked — no needless tap",
    ev(`tsheet.trip.place`) === "Osaka, Osaka, Japan", ev(`tsheet.trip.place`));

  openSheet();
  ev(`document.getElementById("tsCity").value = "ppk";`);
  omStub([{ name: "Petropavl", admin1: "North Kazakhstan", country: "Kazakhstan", country_code: "KZ", latitude: 54.87, longitude: 69.15 }]);
  await ev(`findCity()`);
  check("a lowercase code is refused in the picker, not auto-picked",
    ev(`tsheet.trip.lat`) == null, ev(`tsheet.trip.place`));
  check("and the user is told to name the town",
    /building or airport code/.test(ev(`document.getElementById("tsErr").textContent`)),
    ev(`document.getElementById("tsErr").textContent`));

  console.log("\n--- 12. the refusal must not NAME the wrong place ---------------");
  /* The bug that survived two releases. Every path correctly refused to build a
     trip to Kazakhstan — and then printed:

       Nothing is called "PPK" — the closest match is "Petropavl, North Kazakhstan".

     Which reads, to anyone looking at their phone, as the app proposing Kazakhstan.
     The user reported "PPK is wrongly classified as somewhere in Kazakhstan" twice
     while the trip logic was already correct, because the MESSAGE was the defect.
     A refusal is the whole answer; repeating the wrong answer undoes it. */
  const NAMES_A_WRONG_PLACE = /kazakh|petropavl/i;

  ev(`tsheet={trip:{id:"t",start:"2099-01-01",end:"2099-01-03",styles:["casual"]},
              isNew:true,matches:[],geo:null};
      document.getElementById("tsErr").textContent="";
      document.getElementById("tsCity").value="PPK";`);
  omStub([{ name: "Petropavl", admin1: "North Kazakhstan", country: "Kazakhstan", country_code: "KZ", latitude: 54.87, longitude: 69.15 }]);
  await ev(`findCity()`);
  const msg = ev(`document.getElementById("tsErr").textContent`);
  check("the picker refuses the code", ev(`tsheet.trip.place||null`) === null, ev(`tsheet.trip`));
  check("and does NOT print the place the geocoder wrongly returned",
    !NAMES_A_WRONG_PLACE.test(msg), msg);
  check("it says what the string actually is, and what to type instead",
    /building or airport code/.test(msg) && /town/.test(msg), msg);

  ev(`home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672};`);
  ev(`
    fetch = async (url) => {
      const u = String(url);
      if (u.indexOf("/triage") >= 0) return { ok:true, json: async () => (
        {isTrip:true, city:"PPK", type:"business", confidence:0.9, reason:"offsite"}) };
      return { ok:true, json: async () => ({ results: [
        { name:"Petropavl", admin1:"North Kazakhstan", country:"Kazakhstan", country_code:"KZ",
          latitude:54.87, longitude:69.15 }] }) };
    };`);
  const vr = await ev(`triageCandidate({title:"Team sync",hint:"PPK",nights:1,
                       start:"2026-09-02",end:"2026-09-03"})`);
  check("the automatic path refuses it too", vr.decision === "ask", vr);
  check("and its reason names no country nobody mentioned",
    !NAMES_A_WRONG_PLACE.test(JSON.stringify(vr)), vr);

  // Nothing anywhere in the shipped page may put that string in front of a person.
  const pageSrc = fs.readFileSync(HTML, "utf8");
  const codeOnly = pageSrc
    .replace(/\/\*[\s\S]*?\*\//g, "")               // block comments, including continuations
    .split("\n").filter(l => !/^\s*\/\//.test(l))    // line comments
    .join("\n");
  check("no user-facing string in the page mentions the wrong place",
    !NAMES_A_WRONG_PLACE.test(codeOnly),
    codeOnly.split("\n").filter(l => NAMES_A_WRONG_PLACE.test(l)).slice(0, 3));

  console.log("\n--- 13. codes the user has TAUGHT are looked up, not guessed ----");
  /* The user's own diagnosis, 2026-08-24: "it's always letting LLM decide and not
     overwriting with deterministic locations". Correct. Every fix before this one
     was a better REFUSAL — the app still had to infer what "PPK" meant, and both a
     122B model and a fuzzy geocoder will supply an answer for that with total
     confidence. A table cannot be 85% sure. */
  ev(`home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672};
      places = [
        {abbr:"PPK", city:"Lawrenceville, NJ", place:"Lawrenceville, New Jersey, US", lat:40.297, lon:-74.729},
        {abbr:"BOS OFF", city:"Boston, MA", place:"Boston, Massachusetts, US", lat:42.36, lon:-71.06}];`);

  const KNOWN = [
    ["PPK", "PPK"], ["ppk", "PPK"],                 // case does not matter
    ["PPK Building 3", "PPK"], ["at PPK-3", "PPK"], // a code inside a longer string
    ["bos off", "BOS OFF"], ["BOSOFF", "BOS OFF"],  // a multi-word code, punctuation-blind
  ];
  for (const [text, want] of KNOWN)
    check(`"${text}" resolves to ${want}`,
      (ev(`knownPlace(${JSON.stringify(text)})`) || {}).abbr === want,
      ev(`knownPlace(${JSON.stringify(text)})`));

  // Whole tokens ONLY. A substring rule would make every word containing the code
  // a false hit, which is the same class of error as the IATA table.
  check("a code buried INSIDE a word is not a match",
    ev(`knownPlace("Klippka")`) === null, ev(`knownPlace("Klippka")`));
  check("an untaught code stays unknown", ev(`knownPlace("LVL")`) === null);
  check("and empty text matches nothing", ev(`knownPlace("")`) === null);

  /* THE POINT: a known code never reaches the model OR the geocoder. Any network
     call here is a test failure by construction. */
  /* The GEOCODER is never consulted for a taught code — that is the promise, and it
     is what the IATA table broke. The model is still asked whether the event is
     travel (a location code can name where you set off from), so it is stubbed here
     rather than forbidden; anything reaching Open-Meteo is a test failure. */
  ev(`fetch = async (u) => {
        if (String(u).indexOf("/triage") >= 0) return { ok:true, json: async () => (
          {isTrip:true, city:null, type:"business", confidence:0.9, reason:"x"}) };
        throw new Error("a taught code must never be geocoded"); };`);
  let kv = await ev(`triageCandidate({title:"Team sync",hint:"PPK Building 3",nights:1,
                     start:"2026-09-02",end:"2026-09-03"})`);
  check("a taught code near home is skipped, without ever being geocoded",
    kv.decision === "skip" && /9 km/.test(kv.why || ""), kv);
  /* Far away, the table fixes the DESTINATION but the model still judges travel —
     see 13b. So this one needs the model to answer; what is asserted here is that
     the coordinates come from the table and not from a geocoder. */
  ev(`fetch = async (url) => {
        if (String(url).indexOf("/triage") >= 0) return { ok:true, json: async () => (
          {isTrip:true, city:"Boston", type:"business", confidence:0.95, reason:"client visit"}) };
        throw new Error("a taught destination must not be geocoded"); };`);
  kv = await ev(`triageCandidate({title:"Client",hint:"BOS OFF",nights:2,
                 start:"2026-09-02",end:"2026-09-04"})`);
  check("a taught code far away becomes a trip to THAT town, ungeocoded",
    kv.decision === "trip" && kv.place === "Boston, Massachusetts, US", kv);
  check("an overnight is still required",
    (await ev(`triageCandidate({title:"Client",hint:"BOS OFF",nights:0,
      start:"2026-09-02",end:"2026-09-02"})`)).decision === "skip");

  // Determinism is the whole point: same input, same answer, every time.
  // The geocoder is never involved, so the destination cannot drift between runs
  // however the model phrases its answer.
  ev(`fetch = async (u) => {
        if (String(u).indexOf("/triage") >= 0) return { ok:true, json: async () => (
          {isTrip:true, city:null, type:"business", confidence:0.9, reason:"x"}) };
        throw new Error("a taught code must never be geocoded"); };`);
  const answers = new Set();
  for (let i = 0; i < 5; i++)
    answers.add(JSON.stringify(await ev(`triageCandidate({title:"Team sync",hint:"PPK",
      nights:1,start:"2026-09-02",end:"2026-09-03"})`)));
  check("five runs give ONE answer — a table cannot be 85% sure",
    answers.size === 1, [...answers]);

  console.log("\n--- 13b. the table answers WHERE, not WHETHER --------------------");
  /* Conflating the two turns "two-day workshop at BOS OFF, joining on Zoom" into a
     trip to Boston — an office is not travel however many days it spans, which the
     triage prompt already says. Raised by the pre-push reviewer, 2026-08-24. */
  ev(`fetch = async () => ({ ok:true, json: async () => (
    {isTrip:false, city:null, type:"business", confidence:0.9, reason:"office, joining remotely"}) });`);
  let kw = await ev(`triageCandidate({title:"Workshop",hint:"BOS OFF / Zoom",nights:2,
                     start:"2026-09-02",end:"2026-09-04"})`);
  check("a far taught place is NOT a trip when the event is not travel",
    kw.decision === "skip", kw);

  // The type comes from the event too: a taught code appears on holidays as well,
  // and hard-coding business puts a beach week on the business packing path.
  ev(`fetch = async () => ({ ok:true, json: async () => (
    {isTrip:true, city:"Boston", type:"vacation", confidence:0.95, reason:"holiday"}) });`);
  kw = await ev(`triageCandidate({title:"Break",hint:"BOS OFF",nights:3,
                 start:"2026-09-02",end:"2026-09-05"})`);
  check("when it IS travel, the taught coordinates are used", 
    kw.decision === "trip" && kw.lat === 42.36 && kw.place === "Boston, Massachusetts, US", kw);
  check("and the trip TYPE comes from the event, not from the table",
    kw.type === "vacation", kw);

  /* The model routinely returns NO city for "BOS OFF" — precisely because it can
     see that is an office code and not a city name. Demanding one anyway threw away
     the destination already in hand and sent the user back to confirming by hand,
     which is the thing this table exists to stop. */
  ev(`fetch = async (url) => {
        if (String(url).indexOf("/triage") >= 0) return { ok:true, json: async () => (
          {isTrip:true, city:null, type:"business", confidence:0.9, reason:"client visit"}) };
        throw new Error("a taught destination must not be geocoded"); };`);
  kw = await ev(`triageCandidate({title:"Client",hint:"BOS OFF",nights:2,
                 start:"2026-09-02",end:"2026-09-04"})`);
  check("a taught place still resolves when the model names no city at all",
    kw.decision === "trip" && kw.place === "Boston, Massachusetts, US", kw);

  /* A model answer naming somewhere ELSE is a different destination, not a
     misreading of the taught one — that is the "Flight to London" case. So it goes
     down the ordinary geocoding road, guards and all, and a name nothing matches is
     asked about rather than silently pinned to the taught coordinates. */
  ev(`fetch = async (u) => {
        if (String(u).indexOf("/triage") >= 0) return { ok:true, json: async () => (
          {isTrip:true, city:"Bost", type:"business", confidence:0.95, reason:"x"}) };
        return { ok:true, json: async () => ({ results: [] }) }; };`);
  kw = await ev(`triageCandidate({title:"Client",hint:"BOS OFF",nights:2,
                 start:"2026-09-02",end:"2026-09-04"})`);
  check("a city the model names that is NOT the taught place is judged on its own",
    kw.decision === "ask", kw);

  console.log("\n--- 13c. a long taught code still matches -----------------------");
  /* The window was capped at four words while the UI accepts a 40-character code,
     so anything longer silently fell back to the model — breaking the one promise
     this table makes. The window is each code's own word count now. */
  ev(`places.push({abbr:"NEW YORK CLIENT OFFICE HQ", city:"New York, NY",
                   place:"New York, New York, US", lat:40.71, lon:-74.0});`);
  check("a five-word code resolves",
    (ev(`knownPlace("meeting at NEW-YORK CLIENT OFFICE HQ tomorrow")`) || {}).abbr
      === "NEW YORK CLIENT OFFICE HQ",
    ev(`knownPlace("meeting at NEW YORK CLIENT OFFICE HQ tomorrow")`));
  check("and a partial run of its words does not",
    ev(`knownPlace("NEW YORK CLIENT")`) === null, ev(`knownPlace("NEW YORK CLIENT")`));

  console.log("\n--- 13c2. the code is not the whole story -----------------------");
  /* A location field can name where you set OFF from, not where you are going.
     "Flight to London" with location PPK is a real trip, and an early skip on the
     code alone buried it for ever — a false negative that no later scan recovers,
     because the event is marked dismissed. Raised by the pre-push reviewer. */
  ev(`places = [{abbr:"PPK", city:"Lawrenceville, NJ", place:"Lawrenceville, New Jersey, US", lat:40.297, lon:-74.729}];
      home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672};`);
  const withTriage = (triage, geo) => ev(`
    fetch = async (u) => {
      if (String(u).indexOf("/triage") >= 0)
        return { ok:true, json: async () => (${JSON.stringify(triage)}) };
      return { ok:true, json: async () => ({ results: ${JSON.stringify(geo || [])} }) }; };`);

  withTriage({ isTrip: true, city: "London", type: "business", confidence: 0.95, reason: "flight" },
    [{ name: "London", admin1: "England", country: "United Kingdom", country_code: "GB", latitude: 51.5, longitude: -0.12 }]);
  let ff = await ev(`triageCandidate({title:"Flight to London",hint:"PPK",nights:1,
                     start:"2026-09-02",end:"2026-09-03"})`);
  check("a trip elsewhere is NOT buried by a local code in the location field",
    ff.decision === "trip" && /London/.test(ff.place), ff);

  withTriage({ isTrip: true, city: "Lawrenceville", type: "business", confidence: 0.9, reason: "x" });
  ff = await ev(`triageCandidate({title:"Team sync",hint:"PPK",nights:1,
                 start:"2026-09-02",end:"2026-09-03"})`);
  check("but when the model names the taught place, the table's coordinates are used",
    ff.decision === "skip" && /9 km/.test(ff.why || ""), ff);

  withTriage({ isTrip: true, city: null, type: "business", confidence: 0.9, reason: "x" });
  ff = await ev(`triageCandidate({title:"Team sync",hint:"PPK",nights:1,
                 start:"2026-09-02",end:"2026-09-03"})`);
  check("and when it names none at all, the taught place is the destination",
    ff.decision === "skip" && /9 km/.test(ff.why || ""), ff);

  withTriage({ isTrip: false, city: null, type: "business", confidence: 0.9, reason: "local office" });
  ff = await ev(`triageCandidate({title:"Team sync",hint:"PPK",nights:1,
                 start:"2026-09-02",end:"2026-09-03"})`);
  check("the model's 'not travel' still ends it", ff.decision === "skip", ff);

  console.log("\n--- 13d. codes that are not written in ASCII --------------------");
  /* An ASCII-only key normalised 東京 to the empty string, so a Japanese code saved
     fine and could then never match — the app kept guessing while claiming it had
     learned it. Raised by the pre-push reviewer, 2026-08-24; this user writes their
     weekly report in Japanese, so it is not a hypothetical. */
  ev(`places = [{abbr:"東京", city:"Tokyo", place:"Tokyo, JP", lat:35.68, lon:139.69},
                {abbr:"PPK", city:"Lawrenceville, NJ", place:"Lawrenceville, New Jersey, US", lat:40.297, lon:-74.729}];`);
  check("a Japanese code has a non-empty key", ev(`abbrKey("東京")`).length > 0, ev(`abbrKey("東京")`));
  check("and it matches when written alone",
    (ev(`knownPlace("東京")`) || {}).abbr === "東京");
  /* Japanese does not space its words, so "東京オフィス" is ONE token. A whole-token
     rule would match only the bare form, which makes the feature nearly useless in
     the language it was just fixed for. Inside such a token a substring match is
     also SAFE in a way it is not for Latin: 東京 inside a longer run still means
     Tokyo, whereas "ppk" inside "Klippka" means nothing. */
  check("and inside a run of characters, where there are no spaces to split on",
    (ev(`knownPlace("東京オフィス")`) || {}).abbr === "東京",
    ev(`knownPlace("東京オフィス")`));
  check("and mixed in among other text",
    (ev(`knownPlace("会議 東京 3F")`) || {}).abbr === "東京");
  check("an untaught Japanese place is still unknown",
    ev(`knownPlace("大阪支社")`) === null, ev(`knownPlace("大阪支社")`));
  check("the Latin whole-token rule is unchanged — no substring matching there",
    ev(`knownPlace("Klippka")`) === null, ev(`knownPlace("Klippka")`));

  // A code that normalises to nothing could never match, so it is refused at entry
  // rather than saved and silently inert.
  check("punctuation alone has no key", ev(`abbrKey("---")`) === "");

  console.log("\n--- 13e. a code cannot be taught the wrong coordinates ----------");
  /* Reading the input boxes again at pick time is how a code gets taught with
     somebody else's coordinates: type "Boston", Find, change the code to PPK, tap a
     result — and PPK is mapped to Boston for ever. Deterministically wrong is worse
     than the guessing this table replaced. Same defect the trip sheet had on
     2026-08-20; raised again here by the pre-push reviewer. */
  ev(`home = {label:"Princeton, NJ", lat:40.3573, lon:-74.6672}; places = [];
      geocodeMany = async () => [{lat:42.36, lon:-71.06, place:"Boston, Massachusetts, US", km:374}];`);
  w.document.getElementById("plAbbr").value = "BOS";
  w.document.getElementById("plCity").value = "Boston";
  await ev(`addPlace()`);
  check("the answers are pinned to the question that produced them",
    ev(`placeMatches.abbr`) === "BOS" && ev(`placeMatches.city`) === "Boston",
    ev(`JSON.stringify({a:placeMatches.abbr,c:placeMatches.city})`));

  const abbrBox = w.document.getElementById("plAbbr");
  abbrBox.value = "PPK";
  abbrBox.dispatchEvent(new w.Event("input", { bubbles: true }));
  check("editing the code drops the stale answers", ev(`placeMatches.list.length`) === 0);
  check("and takes them off the screen too",
    w.document.getElementById("plMatches").innerHTML === "");
  await ev(`pickPlace(0)`);
  check("so there is nothing left to teach the wrong coordinates to",
    ev(`places.length`) === 0, ev(`places`));

  w.document.getElementById("plCity").value = "Lawrenceville";
  ev(`geocodeMany = async () => [{lat:40.297, lon:-74.729, place:"Lawrenceville, New Jersey, US", km:9}];`);
  await ev(`addPlace()`);
  await ev(`pickPlace(0)`);
  check("a fresh lookup teaches the pair that was actually looked up",
    ev(`places[0].abbr`) === "PPK" && ev(`places[0].lat`) === 40.297, ev(`places[0]`));
  check("and the boxes are cleared, so the next code starts empty",
    w.document.getElementById("plAbbr").value === "" && w.document.getElementById("plCity").value === "");

  // A code that normalises to nothing is refused rather than saved and inert.
  w.document.getElementById("plAbbr").value = "---";
  w.document.getElementById("plCity").value = "Boston";
  await ev(`addPlace()`);
  check("a code with nothing to match on is refused at entry",
    ev(`places.length`) === 1 && /no letters or numbers/.test(w.document.getElementById("plErr").textContent),
    w.document.getElementById("plErr").textContent);

  // With nothing taught, the old road is still taken.
  ev(`places = [];`);
  check("an empty table changes nothing", ev(`knownPlace("PPK")`) === null);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
