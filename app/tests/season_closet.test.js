/**
 * season_closet.test.js — the seasonal closet (user, 2026-11-18): "I don't need
 * shorts nor summer pants to be in a part of choices during winter. In summer, I
 * don't need jacket nor sweater." The server decides (server/season.py); pinned here:
 *   - the twin reads the same normal day and the same verdicts as season.py's tests;
 *   - /advice and the push snapshot carry the twelve monthly normals, only when the
 *     cached climate was measured at the current home;
 *   - a cached climate without normals is measured again; one with them is not;
 *   - the item sheet stores the override, "auto" as absence; itemMeta sends it;
 *   - the closet files out-of-season garments under "Other seasons".
 *
 * Loads the REAL app/www/index.html in jsdom. Run: npm test
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
const drain = () => new Promise(r => setTimeout(r, 0));
const page = () => new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
}).window;

// The same Tokyo-like year as server/tests/test_season.py.
const TOKYO = [[1, 10], [2, 11], [5, 14], [10, 19], [15, 23], [19, 26],
               [23, 30], [24, 31], [21, 27], [15, 22], [9, 17], [4, 12]];
const HOME = {label: "Home", postal: "", lat: 35.7, lon: 139.7};
const CLIMATE = {lat: 35.7, lon: 139.7, cold: 5.5, avg: 16, hot: 27.5, months: [], normals: TOKYO, at: 1};
const g = (id, label, category, group, type, roles, warmth, extra = {}) => ({id, label, category, group, type,
  roles, colors: ["navy"], warmth, formality: ["casual"], waterproof: false, count: 1, ...extra});
const SHORTS = g("shorts-0001", "khaki shorts", "bottoms", "bottoms", "shorts", ["bottoms"], 1);
const CHINOS = g("chinos-0001", "navy chinos", "bottoms", "bottoms", "trousers", ["bottoms"], 3);
const SWEATER = g("sweatr-0001", "navy sweater", "mid", "tops", "sweater", ["base", "mid", "outer"], 4);
const JACKET = g("jacket-0001", "field jacket", "outer", "outerwear", "jacket", ["outer"], 3);
const COAT = g("coat00-0001", "wool coat", "outer", "outerwear", "coat", ["outer"], 4);
const PUFFER = g("puffer-0001", "down puffer", "outer", "outerwear", "puffer", ["outer"], 5);
const SHIRT = g("shirt0-0001", "oxford shirt", "base", "tops", "shirt", ["base", "mid", "outer"], 2);
const SANDALS = g("sandal-0001", "sandals", "footwear", "footwear", "sandals", ["footwear"], 1);
const TEE = g("tee000-0001", "white tee", "base", "tops", "t_shirt", ["base"], 1);
const N = (lo, hi) => ({lo, hi});
const JAN = N(1, 10), JUL = N(23, 30), NOV = N(9, 17);

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const disk = async k => JSON.parse(await ev(`prefGet(${JSON.stringify(k)},"null")`) || "null");
  const oos = (item, slot, n) => ev(`outOfSeason(${JSON.stringify(item)},${JSON.stringify(slot)},${JSON.stringify(n)})`);

  console.log("\n--- the twin agrees with season.py ---------------------------------");
  ev(`home=${JSON.stringify(HOME)}; climate=${JSON.stringify(CLIMATE)}`);
  const at = (y, m, d) => JSON.parse(ev(`JSON.stringify(seasonNormal(new Date(${y},${m - 1},${d})))`));
  const r1 = n => ({lo: Math.round(n.lo * 10) / 10, hi: Math.round(n.hi * 10) / 10});
  check("mid-July is July's normal", JSON.stringify(r1(at(2026, 7, 16))) === JSON.stringify({lo: 23, hi: 30}), at(2026, 7, 16));
  check("1 July reads off the line (21.1, 28.1)", JSON.stringify(r1(at(2026, 7, 1))) === JSON.stringify({lo: 21.1, hi: 28.1}), at(2026, 7, 1));
  check("31 January reads off the line (1.5, 10.5)", JSON.stringify(r1(at(2026, 1, 31))) === JSON.stringify({lo: 1.5, hi: 10.5}), at(2026, 1, 31));
  check("1 January reads between December and January", (() => { const n = at(2026, 1, 1); return n.lo > 1 && n.lo < 4; })(), at(2026, 1, 1));
  check("shorts and sandals out in January", oos(SHORTS, "bottoms", JAN) && oos(SANDALS, "footwear", JAN));
  check("shorts in season in July", !oos(SHORTS, "bottoms", JUL));
  check("sweater and jacket out in July", oos(SWEATER, "mid", JUL) && oos(JACKET, "outer", JUL) && oos(SWEATER, "base", JUL));
  check("coat in season in November, puffer not", !oos(COAT, "outer", NOV) && oos(PUFFER, "outer", NOV));
  check("puffer in season in January", !oos(PUFFER, "outer", JAN));
  check("overrides: all / warm / cold", !oos({...SHORTS, season: "all"}, "bottoms", JAN)
    && oos({...CHINOS, season: "warm"}, "bottoms", NOV) && !oos({...CHINOS, season: "warm"}, "bottoms", JUL)
    && oos({...CHINOS, season: "cold"}, "bottoms", JUL) && !oos({...CHINOS, season: "cold"}, "bottoms", JAN));
  check("warm/cold split at 12C with no gap", oos({...CHINOS, season: "warm"}, "bottoms", N(11.9, 20))
    && !oos({...CHINOS, season: "warm"}, "bottoms", N(12, 20))
    && !oos({...CHINOS, season: "cold"}, "bottoms", N(11.9, 20)) && oos({...CHINOS, season: "cold"}, "bottoms", N(12, 20)));
  check("leg floor boundary 11.9 / 12.0", ev(`tooColdForLegs(${JSON.stringify(SHORTS)},11.9)`) && !ev(`tooColdForLegs(${JSON.stringify(SHORTS)},12)`));
  check("a shirt is in season in January (it's a base)", ev(`inSeasonNow(${JSON.stringify(SHIRT)},${JSON.stringify(JAN)})`));

  console.log("\n--- normals only from a climate measured at this home -------------");
  check("climateNormals with this home", JSON.stringify(ev("JSON.stringify(climateNormals())")) === JSON.stringify(JSON.stringify(TOKYO)));
  ev(`home={...home, lat:51.5, lon:-0.1}`);
  check("none after moving house", ev("climateNormals()") === null);
  ev(`home=${JSON.stringify(HOME)}; climate={...climate, normals:[[5,1]].concat(climate.normals.slice(1))}`);
  check("malformed normals refused", ev("climateNormals()") === null);
  ev(`climate=${JSON.stringify(CLIMATE)}`);

  console.log("\n--- re-measured once when the cache predates the normals ----------");
  let climateCalls = 0;
  w.fetch = async (url, opts) => {
    if (String(url).endsWith("/climate")) { climateCalls++;
      return {ok: true, status: 200, json: async () => ({cold: 5.5, avg: 16, hot: 27.5, months: [], normals: TOKYO, years: 10})}; }
    return {ok: true, status: 200, json: async () => ({})};
  };
  await ev("refreshClimate()"); await drain();
  check("a full cache is not measured again", climateCalls === 0, climateCalls);
  ev(`climate={...climate}; delete climate.normals`);
  await ev("refreshClimate()"); await drain();
  check("a cache without normals is measured again", climateCalls === 1, climateCalls);
  check("and keeps them", ev("climateNormals()") !== null);
  // The closet drawn before they arrived is filed again once they do.
  const SUMMER = {...CHINOS, id: "summer-0001", label: "summer-only trousers", season: "warm"};
  const WINTER = {...CHINOS, id: "winter-0001", label: "winter-only trousers", season: "cold"};
  ev(`climate={...climate}; delete climate.normals`);
  await ev(`closet=${JSON.stringify([SUMMER, WINTER])}; closetFolded=new Set(); renderCloset()`); await drain(); await drain();
  check("no normals yet: no 'Other seasons'", !/Other seasons/.test(w.document.getElementById("closetGrid").textContent));
  await ev("refreshClimate()"); await drain(); await drain();
  check("once they arrive the closet is filed by season", /Other seasons/.test(w.document.getElementById("closetGrid").textContent));

  console.log("\n--- requests carry the normals ------------------------------------");
  const sent = [];
  w.fetch = async (url, opts) => {
    if (String(url).endsWith("/advice")) { sent.push(JSON.parse(opts.body));
      return {ok: true, status: 200, json: async () => ({weather: {lo: 8, hi: 12, desc: "Clear", rain: 0, wind: 2, code: 0,
        date: new Date().toISOString().slice(0, 10)}, outfit: {base: "white tee", bottoms: "navy chinos"},
        outfit_text: "x", source: "llm", picks: {base: TEE.id, bottoms: CHINOS.id}, closetUsed: true, missing: []})}; }
    return {ok: true, status: 200, json: async () => ({})};
  };
  await ev(`closet=${JSON.stringify([TEE, CHINOS, SHORTS])}; wearLog=[]; lastWorn={}; saveCloset()`);
  ev(`state.lat=35.7; state.lon=139.7; state.city=""`);
  await ev("run()"); await drain();
  check("/advice carries normals", sent.length && JSON.stringify(sent[0].normals) === JSON.stringify(TOKYO), sent[0] && sent[0].normals);
  const snap = await disk("oa.pushPayload");
  check("the push snapshot carries normals", snap && JSON.stringify(snap.normals) === JSON.stringify(TOKYO), snap && snap.normals);
  ev(`home={...home, lat:51.5, lon:-0.1}`);
  await ev("run()"); await drain();
  check("no normals after moving house", sent.length >= 2 && !("normals" in sent[sent.length - 1]), sent[sent.length - 1]);
  ev(`home=${JSON.stringify(HOME)}`);

  console.log("\n--- the override: stored, sent ------------------------------------");
  check("itemMeta sends a non-auto season", ev(`itemMeta(${JSON.stringify({...SHORTS, season: "warm"})}).season`) === "warm");
  check("itemMeta leaves auto out", ev(`"season" in itemMeta(${JSON.stringify({...SHORTS, season: "auto"})})`) === false);
  check("itemMeta drops an unknown season", ev(`"season" in itemMeta(${JSON.stringify({...SHORTS, season: "x"})})`) === false);
  check("the sheet has the picker with four choices", w.document.querySelectorAll("#shSeason option").length === 4);

  console.log("\n--- the closet files out-of-season garments apart -----------------");
  // Today's real date decides; pick a garment out of season NOW whatever the month.
  const n = JSON.parse(ev("JSON.stringify(seasonNormal())"));
  const warmNow = !ev(`outOfSeason(${JSON.stringify({...CHINOS, season: "warm"})},"bottoms",${JSON.stringify(n)})`);
  const off = {...CHINOS, id: "offsea-0001", label: "off-season trousers", season: warmNow ? "cold" : "warm"};
  const on = {...CHINOS, id: "onsea0-0001", label: "all-year trousers", season: "all"};
  await ev(`closet=${JSON.stringify([on, off])}; closetFolded=new Set(); renderCloset()`); await drain(); await drain();
  const grid = w.document.getElementById("closetGrid");
  const offBox = grid.querySelector(".offSeason");
  check("an 'Other seasons' heading appears", /Other seasons/.test(grid.textContent));
  check("the off-season garment is under it", offBox && offBox.querySelector(`[data-id="${off.id}"]`) !== null);
  check("the all-year garment is not", offBox && offBox.querySelector(`[data-id="${on.id}"]`) === null
    && grid.querySelector(`[data-id="${on.id}"]`) !== null);
  ev(`home=null`);
  await ev(`renderCloset()`); await drain(); await drain();
  check("no climate: no 'Other seasons'", !/Other seasons/.test(w.document.getElementById("closetGrid").textContent));

  console.log("\n--- a cold leg gap is not answered by summer legs ------------------");
  // Pre-push gate, 2026-11-24: shorts in the wash suppressed the bottoms gap, and
  // adding another pair of shorts erased it, though warm trousers were still wanted.
  const SHORTS2 = {...SHORTS, id: "shorts-0002", label: "blue shorts"};
  await ev(`closet=${JSON.stringify([TEE, SHORTS, SHORTS2])}; userRules=[]; saveCloset()`);
  check("withheld shorts excuse no bottoms gap at 3C",
    JSON.stringify(ev(`ownershipGaps(["bottoms"],3,[${JSON.stringify(TEE.id)},${JSON.stringify(SHORTS.id)}])`)) === JSON.stringify(["bottoms"]),
    ev(`ownershipGaps(["bottoms"],3,[${JSON.stringify(TEE.id)},${JSON.stringify(SHORTS.id)}])`));
  check("withheld chinos still do", JSON.stringify(ev(`(closet.push(${JSON.stringify(CHINOS)}),
    ownershipGaps(["bottoms"],3,[${JSON.stringify(TEE.id)},${JSON.stringify(SHORTS.id)}]))`)) === "[]");
  const today = new Date().toISOString().slice(0, 10);
  await ev(`gaps=[{slot:"bottoms",day:"${today}",lo:3,hi:8,at:3}]; clearGapsFilledBy(${JSON.stringify(SHORTS2)})`);
  await drain();
  check("another pair of shorts leaves the gap", ev("gaps.length") === 1, ev("JSON.stringify(gaps)"));
  await ev(`clearGapsFilledBy(${JSON.stringify(CHINOS)})`); await drain();
  check("warm trousers answer it", ev("gaps.length") === 0, ev("JSON.stringify(gaps)"));

  // A summer dress is legs too: another one neither suppresses nor clears the base gap.
  const DRESS1 = {id: "dress0-0001", label: "sundress", category: "base", group: "onepiece", type: "dress",
    roles: ["base"], colors: ["red"], warmth: 1, formality: ["casual"], waterproof: false, count: 1};
  const DRESS2 = {...DRESS1, id: "dress0-0002", label: "second sundress"};
  await ev(`closet=${JSON.stringify([DRESS1, DRESS2])}; saveCloset()`);
  check("a withheld summer dress excuses no base gap at 3C",
    JSON.stringify(ev(`ownershipGaps(["base"],3,[${JSON.stringify(DRESS1.id)}])`)) === JSON.stringify(["base"]));
  await ev(`gaps=[{slot:"base",day:"${today}",lo:3,hi:8,at:3}]; clearGapsFilledBy(${JSON.stringify(DRESS2)})`);
  await drain();
  check("another summer dress leaves the base gap", ev("gaps.length") === 1, ev("JSON.stringify(gaps)"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
