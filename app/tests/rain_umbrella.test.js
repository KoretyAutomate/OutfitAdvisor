/**
 * rain_umbrella.test.js — rain never chooses a garment (user, 2026-10-11: "Rain gear
 * doesn't matter, it can go with an umbrella"). Twin of engine.py: the offline
 * recommender dresses a rainy day exactly like a dry one and says to take an umbrella.
 * Snow is not rain: it still gets waterproof boots and a parka.
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
const day = (extra = {}) => ({lo: 24, hi: 30, swing: 6, rain: 0, wind: 2, code: 3, morning: 28, midday: 30,
  evening: 27, isRain: false, isSnow: false, ...extra});

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w.eval("appReady");
  const rec = d => w.eval(`recommend(${JSON.stringify(d)},"man","casual")`);
  for (const t of [28, 12]) {
    const dry = rec(day({morning: t, lo: t - 2, hi: t + 2}));
    const wet = rec(day({morning: t, lo: t - 2, hi: t + 2, rain: 93, isRain: true, code: 63}));
    check(`${t}°: a rainy day gets the dry day's outer`, wet.outer === dry.outer, [wet.outer, dry.outer]);
    check(`${t}°: …and the dry day's shoes`, wet.footwear === dry.footwear, [wet.footwear, dry.footwear]);
    check(`${t}°: the tip says umbrella`, /umbrella/.test(wet.tip) && !/waterproof/i.test(wet.tip), wet.tip);
  }
  const snow = rec(day({morning: -3, lo: -5, hi: 0, isSnow: true, code: 73}));
  check("snow still gets waterproof boots and a parka",
    /waterproof/i.test(snow.footwear) && /parka/i.test(snow.outer), [snow.footwear, snow.outer]);
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
