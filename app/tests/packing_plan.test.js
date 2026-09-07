/**
 * packing_plan.test.js — "a Tokyo trip cannot be survived with 2 pants" (user, 2026-09-07).
 *
 * The phone's half of the packing round: the request says how far from home the
 * trip is (a distance, never a place), the sheet shows the first mornings the
 * server planned with day 1 marked as the travel day, and a shortfall is headed
 * "Short for the trip", not "You don't own".
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * Run: npm test   (or: node tests/packing_plan.test.js)
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
const page = () => new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
}).window;
const drain = () => new Promise(r => setTimeout(r, 0));

const day = n => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
const TRIP = {id: "t1", place: "Tokyo, Japan", start: day(3), end: day(17), type: "business",
  lat: 35.68, lon: 139.77, styles: ["smart", "casual"], packed: [], notifyDays: 2};
const CLOSET = [
  {id: "b1", label: "navy chinos", category: "bottoms", group: "bottoms", type: "chinos", roles: ["bottoms"],
   colors: ["navy"], warmth: 2, formality: ["casual", "smart"], waterproof: false, count: 1, dirty: 0},
  {id: "t1", label: "white shirt", category: "base", group: "tops", type: "shirt", roles: ["base"],
   colors: ["white"], warmth: 1, formality: ["smart"], waterproof: false, count: 2, dirty: 0},
  {id: "s1", label: "white sneakers", category: "footwear", group: "footwear", type: "sneakers", roles: ["footwear"],
   colors: ["white"], warmth: 1, formality: ["casual"], waterproof: false, count: 1, dirty: 0},
];
const DAYS = [0, 1, 2].map(i => ({date: day(3 + i), lo: 16, hi: 24, desc: "Clear", rain: 5, wind: 3, code: 1, emoji: "🌤️"}));
const REPLY = {
  trip: {nDays: 15, type: "business", styles: ["smart", "casual"], truncated: false},
  forecast: {mode: "forecast", days: DAYS, summary: {mode: "forecast", nDays: 15, loMin: 14, hiMax: 25, rainDays: 1, isSnow: false}},
  pack: [{id: "b1", category: "bottoms", label: "navy chinos", qty: 1, why: "a"},
         {id: "t1", category: "base", label: "white shirt", qty: 2, why: "b"},
         {id: "s1", category: "footwear", label: "white sneakers", qty: 1, why: "c"}],
  gaps: [{category: "bottoms", need: "1 pairs for 15 days — a wash every ~3 days"}],
  packing_text: "• Bottoms: the chinos",
  closetUsed: true,
  travel: true,
  plan: [
    {date: DAYS[0].date, travel: true,  picks: {inner: null, base: "t1", mid: null, outer: null, bottoms: "b1", footwear: "s1", accessories: null}},
    {date: DAYS[1].date, travel: false, picks: {inner: null, base: "t1", mid: null, outer: null, bottoms: "b1", footwear: null, accessories: null}},
    {date: DAYS[2].date, travel: false, picks: {inner: null, base: null, mid: null, outer: null, bottoms: "b1", footwear: "s1", accessories: null}},
  ],
};

(async () => {
  const w = page();
  await w.eval("appReady");
  await w.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  w.eval(`home={label:"Lawrenceville, NJ",postal:"",lat:40.3,lon:-74.7}`);
  const sent = [];
  w.fetch = async (url, opts) => {
    if (String(url).endsWith("/packing")) { sent.push(JSON.parse(opts.body)); return {ok: true, status: 200, json: async () => REPLY}; }
    return {ok: true, status: 200, json: async () => ({})};
  };

  console.log("\n--- 1. the request says how far, never where -------------------");
  await w.eval(`openPacking(${JSON.stringify(TRIP)})`);
  await drain(); await drain();
  check("one /packing request went out", sent.length === 1, sent.length);
  const km = sent[0] && sent[0].travelKm;
  check("it carries the distance from home in km", typeof km === "number" && km > 10000 && km < 11500, km);
  check("and still no place name", !JSON.stringify(sent[0]).includes("Tokyo"), Object.keys(sent[0] || {}));

  console.log("\n--- 2. the first mornings are on the sheet -------------------------");
  const doc = w.document;
  const daysShown = [...doc.querySelectorAll("#pkPlan .planDay")];
  check("three mornings are laid out", daysShown.length === 3, daysShown.length);
  check("the first is marked as the travel day", /travel day/.test(daysShown[0] && daysShown[0].textContent));
  check("the others are not", daysShown.slice(1).every(d => !/travel day/.test(d.textContent)));
  const tiles0 = daysShown[0] ? daysShown[0].querySelectorAll(".wearIt").length : 0;
  check("day 1 shows one tile per packed pick", tiles0 === 3, tiles0);
  check("a tile names the garment", /navy chinos/.test(daysShown[0] && daysShown[0].textContent));
  check("the heading reads as a plan", /Your first mornings/.test(doc.getElementById("pkPlan").textContent));

  console.log("\n--- 3. a shortfall is a wash schedule, not a missing item --------");
  const gaps = doc.getElementById("pkGaps").textContent;
  check("headed 'Short for the trip'", /Short for the trip/.test(gaps) && !/don't own/.test(gaps), gaps.slice(0, 80));
  check("and it says how often to wash", /wash every/.test(gaps));

  console.log("\n--- 4. without a home, no distance is claimed ----------------------");
  w.eval("home=null");
  await w.eval(`openPacking(${JSON.stringify(TRIP)})`);
  await drain();
  check("travelKm is simply absent", sent.length === 2 && !("travelKm" in sent[1]), sent[1] && Object.keys(sent[1]));

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
