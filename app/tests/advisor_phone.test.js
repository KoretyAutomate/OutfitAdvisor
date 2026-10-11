/**
 * advisor_phone.test.js — the phone with ONE advisor (2026-10-11).
 *
 * Pinned (raised by the pre-push reviewer):
 *   - a profile change re-asks even after a restart (no coordinates kept);
 *   - an older request's answer never replaces a newer one;
 *   - offline with no network at all, today's saved advice and its weather are shown.
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
const WX = {lo: 12, hi: 20, desc: "Cloudy", rain: 10, wind: 3, code: 3, emoji: "☁️", swing: 8, feelsLo: 11,
  feelsHi: 19, morning: 13, midday: 19, evening: 15, isRain: false, isSnow: false, date: "2026-10-11"};

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w.eval("appReady");
  const ev = s => w.eval(s);

  console.log("\n--- 1. a profile change re-asks after a restart ------------------");
  ev(`lastRes = {weather: ${JSON.stringify(WX)}, outfit: {}, text: "x", source: "llm"}; state.lat = null;
      window.__asked = 0; run = async () => { window.__asked++; };`);
  ev("reaskAdvisor()");
  check("no coordinates kept, still asks — run() resolves the city or GPS", ev("window.__asked") === 1);

  console.log("\n--- 2. the newest request wins -------------------------------------");
  const w2 = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w2.eval("appReady");
  w2.eval(`state.lat = 40.3; state.lon = -74.6; state.style = "smart";
    window.__resolve = [];
    getAdvice = () => new Promise(r => window.__resolve.push(r));`);
  const first = w2.eval("run()");
  await new Promise(r => setTimeout(r, 10));
  w2.eval(`state.style = "active"`);
  const second = w2.eval("run()");
  await new Promise(r => setTimeout(r, 10));
  const ans = s => ({weather: WX, outfit: {base: s}, text: `• ${s}`, source: "llm", picks: null});
  w2.eval(`window.__resolve[1](${JSON.stringify(ans("active pick"))})`); await second;
  w2.eval(`window.__resolve[0](${JSON.stringify(ans("smart pick"))})`); await first;
  check("the older (smart) answer, arriving last, does not replace the newer", w2.eval("lastText") === "• active pick",
    w2.eval("lastText"));
  const saved = JSON.parse(w2.localStorage.getItem("oa.today") || "{}");
  check("…nor the saved copy", saved.outfit_text === "• active pick", saved.outfit_text);

  console.log("\n--- 3. offline with no network at all ------------------------------");
  w.localStorage.setItem("oa.today", JSON.stringify({day: ev("todayISO()"), outfit: {base: "navy polo"},
    outfit_text: "• Navy polo", picks: {base: "i1"}, closetUsed: true, weather: WX}));
  ev(`fetch = async () => { throw new Error("offline"); };
      fetchWeatherLocal = async () => { throw new Error("offline"); };`);
  let off = null, error = null;
  try { off = await ev("getAdvice(40.3,-74.6)"); } catch (e) { error = String(e); }
  check("today's saved advice is shown with its own weather", off && off.source === "saved"
    && off.text === "• Navy polo" && off.weather && off.weather.hi === 20, off || error);

  // Raised by the pre-push reviewer, 2026-10-11: with the forecast service UP, the
  // saved outfit still shows the weather it was chosen for.
  ev(`fetchWeatherLocal = async () => (${JSON.stringify({...WX, hi: 30, lo: 25})});`);
  const off2 = await ev("getAdvice(40.3,-74.6)");
  check("saved advice keeps the weather it was chosen for", off2.source === "saved" && off2.weather.hi === 20,
    off2.weather);

  // Raised by the pre-push reviewer, 2026-10-11: a notification wear survives ANY
  // snapshot rebuild, not only a closet save.
  ev(`closet=[{id:"itm-tee00001",label:"tee",category:"base",group:"tops",type:"t_shirt",roles:["base"],
      colors:["white"],warmth:1,formality:["casual"],waterproof:false,count:1}]; wearLog=[]; wearSeen="[]";`);
  w.localStorage.setItem("oa.wearlog", JSON.stringify([{itemId: "itm-tee00001", wornAt: Date.now() - 60000}]));
  await ev("savePushPayload()");
  const pay = JSON.parse(w.localStorage.getItem("oa.pushPayload") || "{}");
  const tee = (pay.closet || []).find(i => i.id === "itm-tee00001");
  check("the native wear holds the tee in the snapshot", !tee || tee.availableCount === 0, pay.closet);

  // Raised by the pre-push reviewer, 2026-10-11: closet marked complete, but the
  // saved advice was generic — it is not shown again.
  w.localStorage.setItem("oa.today", JSON.stringify({day: ev("todayISO()"), outfit: {base: "Cotton T-shirt"},
    outfit_text: "• Cotton T-shirt", picks: null, closetUsed: false, weather: WX}));
  ev(`closetComplete = true; fetch = async () => { throw new Error("offline"); };
      fetchWeatherLocal = async () => (${JSON.stringify(WX)});`);
  const off3 = await ev("getAdvice(40.3,-74.6)");
  check("a generic saved answer is not shown once the closet is complete", off3.source === "offline", off3.source);
  ev("closetComplete = false;");

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
