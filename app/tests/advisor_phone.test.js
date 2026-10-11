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
      colors:["white"],warmth:1,formality:["casual"],waterproof:false,count:1}]; wearLog=[]; nativeSeen=new Set();`);
  // The notification writes only its own queue (one writer per key).
  w.localStorage.setItem("oa.nativeWears", JSON.stringify([{itemId: "itm-tee00001", wornAt: Date.now() - 60000,
                                                            key: "n1-itm-tee00001"}]));
  await ev("savePushPayload()");
  const pay = JSON.parse(w.localStorage.getItem("oa.pushPayload") || "{}");
  const tee = (pay.closet || []).find(i => i.id === "itm-tee00001");
  check("the native wear holds the tee in the snapshot", !tee || tee.availableCount === 0, pay.closet);
  check("…and the snapshot says it is folded in, so the worker does not hold it twice",
    (pay.nativeSeen || []).includes("n1-itm-tee00001"), pay.nativeSeen);

  // Raised by the pre-push reviewer, 2026-10-11: closet marked complete, but the
  // saved advice was generic — it is not shown again.
  w.localStorage.setItem("oa.today", JSON.stringify({day: ev("todayISO()"), outfit: {base: "Cotton T-shirt"},
    outfit_text: "• Cotton T-shirt", picks: null, closetUsed: false, weather: WX}));
  ev(`closetComplete = true; fetch = async () => { throw new Error("offline"); };
      fetchWeatherLocal = async () => (${JSON.stringify(WX)});`);
  const off3 = await ev("getAdvice(40.3,-74.6)");
  check("a generic saved answer is not shown once the closet is complete", off3.source === "offline", off3.source);
  ev("closetComplete = false;");

  // Raised by the pre-push reviewer, 2026-10-11: another city's saved advice is
  // not shown under the new city's name.
  w.localStorage.setItem("oa.today", JSON.stringify({day: ev("todayISO()"), outfit: {base: "navy polo"},
    outfit_text: "• Navy polo", picks: {base: "i1"}, closetUsed: true, weather: WX, place: "New York"}));
  ev(`state.place = "Singapore"; fetch = async () => { throw new Error("offline"); };
      fetchWeatherLocal = async () => (${JSON.stringify(WX)});`);
  const off4 = await ev("getAdvice(1.35,103.8)");
  check("New York's saved advice is not shown for Singapore", off4.source === "offline", off4.source);

  // Raised by the pre-push reviewer, 2026-10-11: the notification logs a wear WHILE
  // the page is mid-save. One writer per key — the wear lands in the receiver's own
  // queue, which the page never writes, and is folded in on the next save.
  ev(`closet=[{id:"itm-tee00002",label:"tee",category:"base",group:"tops",type:"t_shirt",roles:["base"],
      colors:["white"],warmth:1,formality:["casual"],waterproof:false,count:1}]; wearLog=[]; nativeSeen=new Set();`);
  w.localStorage.removeItem("oa.nativeWears");
  ev(`window.__realSet = prefSet; prefSet = async (k, v) => {
        if (k === "oa.lastWorn" && !window.__injected) {
          window.__injected = true;   // the receiver runs between the page's awaited writes
          localStorage.setItem("oa.nativeWears", JSON.stringify([{itemId: "itm-tee00002",
            wornAt: Date.now() - 1000, key: "n9-itm-tee00002"}]));
          localStorage.setItem("oa.nativeWore", JSON.stringify({day: todayISO(), map: {base: "itm-tee00002"}}));
        }
        return window.__realSet(k, v); };`);
  await ev("saveCloset()");
  check("the mid-save wear is still in the receiver's queue",
    (JSON.parse(w.localStorage.getItem("oa.nativeWears") || "[]")).length === 1);
  ev("prefSet = window.__realSet");
  await ev("saveCloset()");
  check("…and the next save folds it into the wear log",
    JSON.parse(w.localStorage.getItem("oa.wearlog") || "[]").some(x => x.itemId === "itm-tee00002"),
    w.localStorage.getItem("oa.wearlog"));

  // Raised by the pre-push reviewer, 2026-10-11 (P1): a folded queue wear is SAVED
  // before it is acknowledged, so a reload cannot lose it.
  ev(`wearLog=[]; nativeSeen=new Set(); nativeWoreSeen="";`);
  w.localStorage.setItem("oa.wearlog", "[]");
  w.localStorage.setItem("oa.nativeWears", JSON.stringify([{itemId: "itm-p1", wornAt: Date.now() - 1000, key: "nP1"}]));
  await ev("mergeNativeWears()");
  check("the folded wear is on disk before its key is acknowledged",
    JSON.parse(w.localStorage.getItem("oa.wearlog")).some(x => x.itemId === "itm-p1")
    && JSON.parse(w.localStorage.getItem("oa.nativeSeen")).includes("nP1"));

  // Raised by the pre-push reviewer, 2026-10-11: an undo of a notification-logged
  // outfit is not undone by re-adopting the same day record.
  w.localStorage.setItem("oa.nativeWore", JSON.stringify({day: ev("todayISO()"), map: {base: "itm-p1"}}));
  ev(`woreLogged=null; woreDay=null;`);
  await ev("mergeNativeWears()");
  check("the receiver's record is adopted once", ev("JSON.stringify(woreLogged)") === '{"base":"itm-p1"}');
  ev(`woreLogged=null; woreDay=null;`);       // the wearer undoes it
  await ev("mergeNativeWears()");
  check("…and not again after an undo", ev("woreLogged") === null, ev("JSON.stringify(woreLogged)"));

  // Raised by the pre-push reviewer, 2026-10-11: packing sees each garment's roles.
  ev(`closet=[{id:"itm-swtr",label:"sweater",category:"base",group:"tops",type:"sweater",roles:["base","mid","outer"],
      colors:["navy"],warmth:4,formality:["casual"],waterproof:false,count:1}]; wearLog=[];`);
  const pp = ev(`packPayload({start:"2026-10-20",end:"2026-10-22"})`);
  check("the packing payload carries the roles", JSON.stringify(pp[0].roles) === '["base","mid","outer"]', pp[0]);

  // Raised by the pre-push reviewer, 2026-10-11 (P1): the adopted record is saved
  // into the app's own key before it is acknowledged, so a second reload keeps it.
  ev(`woreLogged=null; woreDay=null; nativeWoreSeen="";`);
  w.localStorage.setItem("oa.woreToday", "");
  w.localStorage.setItem("oa.nativeWore", JSON.stringify({day: ev("todayISO()"), map: {base: "itm-p2"}}));
  await ev("mergeNativeWears()");
  const rec = JSON.parse(w.localStorage.getItem("oa.woreToday") || "null");
  check("the adopted record is in the app's own key", rec && rec.map && rec.map.base === "itm-p2", rec);

  // Raised by the pre-push reviewer, 2026-10-11: a queued wear is folded in BEFORE the
  // advice request reads the closet and the recent wears.
  ev(`closet=[{id:"itm-tee00003",label:"tee",category:"base",group:"tops",type:"t_shirt",roles:["base"],
      colors:["white"],warmth:1,formality:["casual"],waterproof:false,count:1}]; wearLog=[]; nativeSeen=new Set(); lastWorn={};`);
  w.localStorage.setItem("oa.nativeWears", JSON.stringify([{itemId: "itm-tee00003", wornAt: Date.now() - 1000, key: "nQ3"}]));
  const bodies = [];
  ev(`fetch = async (u, o) => { window.__b = JSON.parse(o.body); throw new Error("stop"); };
      fetchWeatherLocal = async () => (${JSON.stringify(WX)}); localStorage.removeItem("oa.today");`);
  try { await ev("getAdvice(40.3,-74.6)"); } catch (e) { /* offline after the request — not under test */ }
  const b = ev("window.__b");
  check("the request knows today's notification wear", b && b.recent && b.recent["itm-tee00003"] === 0, b && b.recent);
  check("…and does not offer the worn tee as clean", b && !(b.closet || []).some(i => i.id === "itm-tee00003"),
    b && b.closet);

  // Raised by the pre-push reviewer, 2026-10-11: the same outfit logged again from
  // the notification after an undo is a NEW record (it carries `at`).
  ev(`woreLogged=null; woreDay=null; nativeWoreSeen="";`);
  const rec1 = {day: ev("todayISO()"), map: {base: "itm-p3"}, at: 1};
  w.localStorage.setItem("oa.nativeWore", JSON.stringify(rec1));
  await ev("mergeNativeWears()");
  ev(`woreLogged=null; woreDay=null;`);                       // undone in the app
  w.localStorage.setItem("oa.nativeWore", JSON.stringify({...rec1, at: 2}));   // logged again
  await ev("mergeNativeWears()");
  check("re-logging the same outfit after an undo is adopted again",
    ev("JSON.stringify(woreLogged)") === '{"base":"itm-p3"}', ev("JSON.stringify(woreLogged)"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
