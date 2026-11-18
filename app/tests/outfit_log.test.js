/**
 * outfit_log.test.js — What I wore (user, 2026-11-14): "I want to keep a log of what I
 * wore with parameters which influence decision (occasion, weather, temperature) so
 * that suggestion naturally fits into my taste." PLAN.md, 2026-11-14.
 *
 * Pinned:
 *   - "Wearing it" logs the day: the outfit, the occasion ("" → null) and the RAW weather;
 *     today's record carries the entry and what was served; undo takes both back;
 *   - a correction marks only the slots that differ from what was SERVED — after a
 *     re-roll too; saved unchanged marks nothing;
 *   - /advice and the push snapshot carry the log; the export carries it with today;
 *   - launch heals a crash between the record and the log, both ways, and leaves an
 *     older record (no entry) alone; the raw temperatures survive a restart;
 *   - the notification's queue folds in: three closed-app days all kept, today's from
 *     its own record, never from oa.today;
 *   - pruning: 120 days, 90 entries, 48 KB, the oldest going first;
 *   - swaps the log already holds are left out of `prefers`, unless the day was edited;
 *   - the history list: delete + undo restores the exact entry; an earlier day's edit
 *     changes only the log; today's delete goes through the undo path and stays gone.
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
/* A fresh page; `seed` is put in its storage before any script runs — a restart. */
const page = (seed = {}) => new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  beforeParse(win) { for (const [k, v] of Object.entries(seed)) win.localStorage.setItem(k, v); },
}).window;
const drain = () => new Promise(r => setTimeout(r, 0));
const storage = w => { const o = {}; for (let i = 0; i < w.localStorage.length; i++) {
  const k = w.localStorage.key(i); o[k] = w.localStorage.getItem(k); } return o; };

const WX = {lo:12, hi:20, desc:"Clear", rain:30, wind:4, code:0, emoji:"☀️",
  swing:8, feelsLo:11, feelsHi:20, morning:13, midday:19, evening:16,
  isRain:false, isSnow:false, date:new Date().toISOString().slice(0,10)};
const item = (id, label, category) => ({id, label, category, group: category === "bottoms" ? "bottoms" : "tops",
  type: category === "bottoms" ? "chinos" : "t_shirt", roles: [category], colors: ["navy"], warmth: 2,
  formality: ["casual"], waterproof: false, count: 2});
const CLOSET = [item("tee-000001", "navy tee", "base"), item("tee-000002", "grey tee", "base"),
                item("chino-0001", "beige chinos", "bottoms")];
const OUTFIT = {inner:"", base:"navy tee", mid:"", outer:"", bottoms:"beige chinos", footwear:"", accessories:"", tip:""};
const P = base => ({inner:null, base, mid:null, outer:null, bottoms:"chino-0001", footwear:null, accessories:null});

function capture(w, state) {
  const sent = [];
  w.fetch = async (url, opts) => {
    const u = String(url);
    if (u.endsWith("/advice")) {
      sent.push(JSON.parse(opts.body));
      return {ok:true, status:200, json: async () => ({weather:WX, outfit:OUTFIT, outfit_text:"x", source:"llm",
        picks:P(state.base), closetUsed:true, missing:[], planTemp:15.5, peakTemp:20, rawPlanTemp:15,
        rawPeakTemp:19.5})};
    }
    if (u.endsWith("/export")) { sent.push({export: JSON.parse(opts.body)});
      return {ok:true, status:200, json: async () => ({filename:"x.md", markdown:"#"})}; }
    return {ok:true, status:200, json: async () => ({})};
  };
  return sent;
}

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const log = () => JSON.parse(ev("JSON.stringify(outfitLog)"));
  const disk = async k => JSON.parse(await ev(`prefGet(${JSON.stringify(k)},"null")`) || "null");
  const today = ev("todayISO()");
  const ago = n => ev(`dayISO(Date.now()-${n}*86400000)`);
  const state = {base: "tee-000001"};
  await ev(`closet=${JSON.stringify(CLOSET)}; wearLog=[]; lastWorn={}; saveCloset()`);
  ev(`state.lat=40.7; state.lon=-74.0; state.city=""`);
  const sent = capture(w, state);
  await ev("run()"); await drain();

  console.log("\n--- 1. Wearing it logs the day, with its weather -----------------");
  check("the advice keeps the raw temperatures", ev("lastRes.rawPlanTemp") === 15 && ev("lastRes.rawPeakTemp") === 19.5);
  check("no log before", log().length === 0);
  await w.document.getElementById("dWear").onclick(); await drain();
  const e1 = log()[0];
  check("one entry, today's", log().length === 1 && e1.day === today, log());
  check("the outfit, without empty slots", JSON.stringify(e1.picks) === JSON.stringify({base:"tee-000001", bottoms:"chino-0001"}), e1.picks);
  check("raw temps, rain and wind — not the calibrated 15.5", e1.temp === 15 && e1.peak === 19.5 && e1.rain === 30 && e1.wind === 4, e1);
  check("no occasion set → null", e1.occasion === null, e1.occasion);
  check("accepting the suggestion chose nothing", JSON.stringify(e1.chose) === "[]", e1.chose);
  check("on disk", (await disk("oa.outfitlog")).length === 1);
  const rec1 = await disk("oa.woreToday");
  check("today's record carries the entry and what was served",
    rec1.entry && rec1.entry.day === today && rec1.served && rec1.served.base === "tee-000001", rec1);
  const snap = await disk("oa.pushPayload");
  check("the push snapshot carries the log", snap.worn && snap.worn.length === 1 && Array.isArray(snap.outfitSeen), snap && Object.keys(snap));

  console.log("\n--- 2. the next request carries it ---------------------------------");
  await ev("run()"); await drain();
  const b2 = sent.filter(x => !x.export).pop();
  check("/advice has `worn`", b2.worn && b2.worn.length === 1 && b2.worn[0].temp === 15, b2.worn);

  console.log("\n--- 3. a re-roll changes nothing; a correction is judged against what was SERVED");
  state.base = "tee-000002";
  await ev("run()"); await drain();
  check("re-rolled to the grey tee", ev("lastRes.picks.base") === "tee-000002");
  check("the log still says the navy tee", log()[0].picks.base === "tee-000001");
  ev("openWoreSheet()");
  await ev(`woreDraft={...woreDraft, base:"tee-000002"}; saveWore()`); await drain();
  const e3 = log().find(e => e.day === today);
  check("the grey tee is logged", e3.picks.base === "tee-000002", e3);
  check("only the top was their own choice (vs served, not the re-roll on screen)",
    JSON.stringify(e3.chose) === JSON.stringify(["base"]), e3.chose);
  check("the correction kept the weather it was logged with", e3.temp === 15, e3);
  const snap3 = await disk("oa.pushPayload");
  check("the push snapshot has the corrected outfit (pre-push gate, 2026-11-16)",
    (snap3.worn.find(e => e.day === today) || {picks:{}}).picks.base === "tee-000002", snap3.worn);

  console.log("\n--- 4. undo takes the record and the entry back --------------------");
  await w.document.getElementById("dWear").onclick(); await drain();
  check("today's entry is gone", !log().some(e => e.day === today), log());
  check("…and the record", (await ev(`prefGet("oa.woreToday","")`)) === "");

  console.log("\n--- 5. saved unchanged chooses nothing -----------------------------");
  await w.document.getElementById("dWear").onclick(); await drain();
  ev("openWoreSheet()"); await ev("saveWore()"); await drain();
  check("chose stays empty", JSON.stringify(log().find(e => e.day === today).chose) === "[]", log());

  console.log("\n--- 6. swaps the log holds are not counted twice -------------------");
  const d1 = ago(3), d2 = ago(4);
  await ev(`outfitLog=outfitLog.filter(e=>e.day===todayISO()).concat([
      {day:${JSON.stringify(d1)},occasion:null,temp:14,peak:18,rain:0,wind:2,picks:{base:"tee-000002",bottoms:"chino-0001"},chose:["base"],at:1}]);
    swaps=[{day:${JSON.stringify(d1)},slot:"base",wore:"tee-000002",instead:"tee-000001"},
           {day:${JSON.stringify(d2)},slot:"base",wore:"tee-000002",instead:"tee-000001"}]`);
  check("the logged day's swap is left out — one is not a habit",
    JSON.parse(ev("JSON.stringify(swapSummary(closet))")).length === 0, ev("JSON.stringify(swapSummary(closet))"));
  ev(`outfitLog.find(e=>e.day===${JSON.stringify(d1)}).picks.base="tee-000001"`);
  check("edited to another garment, the swap counts again",
    JSON.parse(ev("JSON.stringify(swapSummary(closet))")).some(x => x.id === "tee-000002" && x.n === 2));
  await ev("saveOutfitLog()");

  console.log("\n--- 7. export carries the log and the phone's today ----------------");
  await ev("shareCloset()"); await drain();
  const ex = sent.filter(x => x.export).pop();
  check("worn and today", ex && ex.export.worn.length === log().length && ex.export.today === today, ex && Object.keys(ex.export));

  console.log("\n--- 8. a restart: raw temps survive; a crash heals both ways --------");
  {
    const seed = storage(w);
    const w2 = page(seed); await w2.eval("appReady");
    check("lastRes still has the raw temperatures", w2.eval("lastRes&&lastRes.rawPlanTemp") === 15, w2.eval("JSON.stringify(lastRes)"));
    // Crashed after the record, before the log.
    const lost = {...seed, "oa.outfitlog": JSON.stringify(JSON.parse(seed["oa.outfitlog"]).filter(e => e.day !== today))};
    const w3 = page(lost); await w3.eval("appReady");
    check("the log's today is restored from the record",
      JSON.parse(w3.eval("JSON.stringify(outfitLog)")).some(e => e.day === today));
    // Crashed after an undo cleared the record, before the log.
    const stale = {...seed, "oa.woreToday": ""};
    const w4 = page(stale); await w4.eval("appReady");
    check("no record → today's entry dropped", !JSON.parse(w4.eval("JSON.stringify(outfitLog)")).some(e => e.day === today));
    // A record from before this build: day and map only.
    const old = {...seed, "oa.woreToday": JSON.stringify({day: today, map: P("tee-000001")})};
    const w5 = page(old); await w5.eval("appReady");
    check("an older record leaves the log alone",
      JSON.parse(w5.eval("JSON.stringify(outfitLog)")).some(e => e.day === today));
  }

  console.log("\n--- 9. the notification's queue: closed-app days all kept ---------");
  {
    const entry = (day, temp) => ({day, occasion:"off", temp, peak:temp+3, rain:0, wind:1,
      picks:{base:"tee-000001", bottoms:"chino-0001"}, chose:[], at:5});
    const seed = {...storage(w), "oa.woreToday": "", "oa.outfitlog": "[]",
      "oa.nativeOutfits": JSON.stringify([{key:"o1", entry:entry(ago(3), 10)}, {key:"o2", entry:entry(ago(2), 11)},
                                          {key:"o3", entry:entry(ago(1), 12)}, {key:"o4", entry:entry(today, 13)}]),
      "oa.nativeWore": JSON.stringify({day: today, map: P("tee-000001"), at: 9, entry: entry(today, 13)}),
      "oa.nativeWoreSeen": "", "oa.nativeOutfitsSeen": "[]"};
    // oa.today says a re-roll made it 30°: the log must not read the weather from there.
    const t = JSON.parse(seed["oa.today"]); t.rawPlanTemp = 30; seed["oa.today"] = JSON.stringify(t);
    const w6 = page(seed); await w6.eval("appReady"); await drain();
    const l6 = JSON.parse(w6.eval("JSON.stringify(outfitLog)"));
    check("three closed-app days and today", l6.length === 4, l6.map(e => e.day));
    check("today from the receiver's record, not oa.today", (l6.find(e => e.day === today) || {}).temp === 13, l6);
    check("acknowledged after the log was saved",
      JSON.parse(w6.localStorage.getItem("oa.nativeOutfitsSeen")).length === 4 &&
      JSON.parse(w6.localStorage.getItem("oa.outfitlog")).length === 4);
    check("today's record now carries the entry", JSON.parse(w6.localStorage.getItem("oa.woreToday")).entry.temp === 13);
  }

  console.log("\n--- 9b. a notification tap while the app is open ----------------");
  {
    const w8 = page({...storage(w), "oa.woreToday": "", "oa.outfitlog": "[]", "oa.nativeOutfits": "[]",
                     "oa.nativeWore": "", "oa.nativeWoreSeen": ""});
    await w8.eval("appReady");
    const ent = {day: today, occasion: "wfh", temp: 9, peak: 12, rain: 0, wind: 1,
                 picks: {base: "tee-000001", bottoms: "chino-0001"}, chose: [], at: 7};
    w8.localStorage.setItem("oa.nativeWore", JSON.stringify({day: today, map: P("tee-000001"), at: 7, entry: ent}));
    await w8.eval("mergeNativeWears()"); await drain();
    const l8 = JSON.parse(w8.eval("JSON.stringify(outfitLog)"));
    check("adopted into the log on resume, no restart needed", l8.length === 1 && l8[0].temp === 9, l8);
  }

  console.log("\n--- 10. pruning -----------------------------------------------------");
  {
    const id = c => c.repeat(64);
    const big = Array.from({length: 100}, (_, n) => ({day: ago(99 - n), occasion: "office", temp: -12.5, peak: -8.25,
      rain: 100, wind: 59.5, picks: {inner:id("a"), base:id("b"), mid:id("c"), outer:id("d"), bottoms:id("e"), footwear:id("f")},
      chose: ["inner","base","mid","outer","bottoms","footwear"], at: 1700000000000}));
    const out = JSON.parse(ev(`JSON.stringify(pruneOutfitLog(${JSON.stringify(big)}))`));
    check("at most 90", out.length <= 90, out.length);
    check("within 48 KB", JSON.stringify(out).length <= 48000, JSON.stringify(out).length);
    check("the OLDEST went", out[out.length - 1].day === today && out[0].day > ago(90), [out[0].day, out.length]);
    const old = JSON.parse(ev(`JSON.stringify(pruneOutfitLog([{day:${JSON.stringify(ago(121))}},{day:${JSON.stringify(ago(120))}}]))`));
    check("older than 120 days goes, 120 stays", old.length === 1 && old[0].day === ago(120), old);
  }

  console.log("\n--- 11. the history list -------------------------------------------");
  {
    const past = ago(3);
    ev("openHistory()");
    const rows = w.document.querySelectorAll("#histList [data-hday]");
    check("one row per day, newest first", rows.length === log().length && rows[0].dataset.hday === today, rows.length);
    const before = JSON.stringify(log().find(e => e.day === past));
    await ev(`deleteHistDay(${JSON.stringify(past)})`); await drain();
    check("deleted", !log().some(e => e.day === past));
    check("with an undo", !!w.document.getElementById("histUndoBtn"));
    await ev("undoHistDelete()"); await drain();
    check("undo restores it exactly", JSON.stringify(log().find(e => e.day === past)) === before);
    const wl = ev("JSON.stringify(wearLog)"), sw = ev("JSON.stringify(swaps)"), rec = await ev(`prefGet("oa.woreToday","")`);
    ev(`outfitLog.find(e=>e.day===${JSON.stringify(past)}).chose=[]`);   // so the edit is what marks it
    ev(`editHistDay(${JSON.stringify(past)})`);
    check("the editor opens", w.document.getElementById("histEditWrap").classList.contains("show"));
    await ev(`histDraft.base="tee-000002"; saveHistEdit()`); await drain();
    const ed = log().find(e => e.day === past);
    check("the day's top changed, and is now their choice", ed.picks.base === "tee-000002" && ed.chose.includes("base"), ed);
    check("nothing else moved: laundry, swaps, today's record",
      ev("JSON.stringify(wearLog)") === wl && ev("JSON.stringify(swaps)") === sw && (await ev(`prefGet("oa.woreToday","")`)) === rec);
    await ev(`deleteHistDay(todayISO())`); await drain();
    check("today's delete is the undo: record and entry", !log().some(e => e.day === today) &&
      (await ev(`prefGet("oa.woreToday","")`)) === "");
    const w7 = page(storage(w)); await w7.eval("appReady");
    check("…and launch does not bring it back", !JSON.parse(w7.eval("JSON.stringify(outfitLog)")).some(e => e.day === today));
  }

  console.log("\n--- 12. the native half (static: Kotlin cannot run here) --------");
  {
    const KT = f => fs.readFileSync(path.join(__dirname, "..", "android", "app", "src", "main", "java", "com",
      "korety", "outfitadvisor", f), "utf8");
    const SRC = fs.readFileSync(HTML, "utf8");
    const ol = KT("OutfitLog.kt"), fb = KT("FeedbackReceiver.kt"), note = KT("OutfitNotification.kt"),
          worker = KT("AdviceWorker.kt");
    const num = (re, src) => +((src.match(re) || [])[1]);
    check("the bounds are the app's", num(/KEEP_DAYS = (\d+)/, ol) === num(/OUTFIT_KEEP_DAYS=(\d+)/, SRC) &&
      num(/const val MAX = (\d+)/, ol) === num(/OUTFIT_MAX=(\d+)/, SRC) &&
      num(/BYTES = (\d+)/, ol) === num(/OUTFIT_BYTES=(\d+)/, SRC));
    check("the queue key is the one the app folds", /KEY_QUEUE = "oa\.nativeOutfits"/.test(ol) &&
      /prefGet\("oa\.nativeOutfits"/.test(SRC));
    check("the notification's action carries the day's context", /putExtra\(FeedbackReceiver\.EXTRA_CONTEXT/.test(note) &&
      /wearContext = advice\.raw\?\.let \{ OutfitLog\.context\(it, occasion\) \}/.test(worker));
    check("the context is the RAW weather", /opt\("rawPlanTemp"\)/.test(ol) && !/opt\("planTemp"\)/.test(ol));
    const onWear = fb.slice(fb.indexOf("private fun onWear"), fb.indexOf("private fun loggedToday"));
    check("the receiver queues the entry and puts it in its day record",
      /OutfitLog\.enqueue\(/.test(onWear) && /it\.put\("entry", entry\)/.test(onWear));
    check("…and still writes none of the app's keys",
      !/putString\(KEY_WEARLOG|putString\(KEY_WORE\b|putString\("oa\.outfitlog"/.test(onWear));
    check("the worker sends the snapshot's log plus the unfolded queue",
      /OutfitLog\.overlay\(p\.optJSONArray\("worn"\), queue, seen/.test(worker) && /body\.put\("worn", worn\)/.test(worker));
    check("…with the snapshot's own acknowledgements", /p\.optJSONArray\("outfitSeen"\)/.test(worker));
    check("oa.today keeps the raw temperatures natively too",
      /\.put\("rawPlanTemp", raw\.opt\("rawPlanTemp"\)\)/.test(worker));
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
