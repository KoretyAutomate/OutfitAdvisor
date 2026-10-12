/**
 * office_days.test.js — office, WFH or a day off (user, 2026-10-12: "I go to the
 * office three times a week and the app should allow me differentiate WFH days and
 * in office days … Today's outfit looks good but not for WFH day").
 *
 * Pinned:
 *   - office days decide the kind of day; other weekdays are WFH, weekends days off;
 *   - each kind has its own style, and the request carries both;
 *   - a tap on the Today screen changes TODAY only, and is undone by choosing the
 *     schedule's own kind;
 *   - saved advice is re-used only for the same kind and style;
 *   - no office days set = nothing about the day is sent (the old behaviour);
 *   - the morning push (Kotlin) reads the same keys, the same way.
 *
 * Loads the REAL app/www/index.html in jsdom. Run: npm test
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
const WORKER = path.join(__dirname, "..", "android", "app", "src", "main", "java", "com", "korety",
  "outfitadvisor", "AdviceWorker.kt");
let passed = 0, failed = 0;
const check = (name, cond, detail = "") => {
  if (cond) { passed++; console.log(`[PASS] ${name}`); }
  else { failed++; console.log(`[FAIL] ${name}  ${JSON.stringify(detail)}`); }
};
const WX = {lo: 12, hi: 20, desc: "Cloudy", rain: 10, wind: 3, code: 3, emoji: "☁️", swing: 8, feelsLo: 11,
  feelsHi: 19, morning: 13, midday: 19, evening: 15, isRain: false, isSnow: false, date: "2026-10-12"};

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const dow = new Date().getDay();
  const ls = w.localStorage;

  console.log("\n--- 1. the schedule ---------------------------------------------");
  check("no office days: no kind, nothing to say", ev("dayKind()") === "");
  check("Monday off the list is WFH", ev(`(state.officeDays=[2,4], scheduledKind(new Date(2026,9,12)))`) === "wfh");
  check("Tuesday on it is an office day", ev("scheduledKind(new Date(2026,9,13))") === "office");
  check("Saturday is a day off", ev("scheduledKind(new Date(2026,9,17))") === "off");

  console.log("\n--- 2. the request -----------------------------------------------");
  ev(`state.style="casual"; state.styleOffice="smart"; state.lat=40.3; state.lon=-74.6;
      fetchWeatherLocal = async () => (${JSON.stringify(WX)});
      fetch = async (u, o) => { if (o && o.body) window.__b = JSON.parse(o.body); throw new Error("stop"); };`);
  const ask = async () => { ev("window.__b=null"); try { await ev("getAdvice(40.3,-74.6)"); } catch (e) {} return ev("window.__b"); };
  ev(`state.officeDays=[${dow}]; dayKindOverride=null;`);
  let b = await ask();
  check("an office day asks for the office style", b.occasion === "office" && b.style === "smart", b);
  ev(`state.officeDays=[${(dow + 1) % 7}];`);
  b = await ask();
  const expect = dow === 0 || dow === 6 ? "off" : "wfh";
  check("any other day asks for the home style", b.occasion === expect && b.style === "casual", b);
  ev("state.officeDays=[];");
  b = await ask();
  check("no schedule: no occasion sent, the one style as before", !("occasion" in b) && b.style === "casual", b);

  console.log("\n--- 3. the Today screen ------------------------------------------");
  ev(`state.officeDays=[${dow}]; dayKindOverride=null; window.__asked=0; window.__realRun=run;
      run=async()=>{window.__asked++;}; lastRes={weather:{},outfit:{},text:"x",occasion:"office",style:"smart"}; paintDay();`);
  check("Office is lit, with the office style", ev(`$("kindSeg").querySelector(".on").dataset.k`) === "office"
    && ev(`$("todayStyleSeg").querySelector(".on").dataset.s`) === "smart");
  ev(`$("kindSeg").querySelector('[data-k="wfh"]').click()`);
  await new Promise(r => setTimeout(r, 20));
  check("tapping WFH makes today WFH, with the home style", ev("dayKind()") === "wfh"
    && ev(`$("todayStyleSeg").querySelector(".on").dataset.s`) === "casual");
  check("…and asks the advisor again", ev("window.__asked") === 1);
  check("…for today only", JSON.parse(ls.getItem("oa.dayKind")).day === ev("todayISO()"));
  check("tomorrow is still what the schedule says", ev(`scheduledKind(new Date(Date.now()+864e5))`) !== "" );
  check("the note says it is a one-day change", /Today only/.test(ev(`$("kindNote").textContent`)));
  ev(`$("todayStyleSeg").querySelector('[data-s="smart"]').click()`);
  await new Promise(r => setTimeout(r, 20));
  check("the style row edits today's kind's style (home), not the office one",
    ev("state.style") === "smart" && ev("state.styleOffice") === "smart" && ls.getItem("oa.style") === "smart");
  ev(`state.style="casual";`);
  ev(`$("kindSeg").querySelector('[data-k="office"]').click()`);
  await new Promise(r => setTimeout(r, 20));
  check("choosing the schedule's own kind clears the override", ev("dayKindOverride") === null
    && ls.getItem("oa.dayKind") === "");
  ev(`dayKindOverride={day:"2020-01-01",kind:"off"}`);
  check("an override from another day is ignored", ev("dayKind()") === "office");

  console.log("\n--- 4. Settings --------------------------------------------------");
  ev(`state.officeDays=[]; paintDay(); $("officeDaysSeg").querySelector('[data-d="1"]').click();`);
  await new Promise(r => setTimeout(r, 20));
  ev(`$("officeDaysSeg").querySelector('[data-d="3"]').click()`);
  await new Promise(r => setTimeout(r, 20));
  check("office days are stored as weekday numbers", ls.getItem("oa.officeDays") === "[1,3]", ls.getItem("oa.officeDays"));
  ev(`$("styleOfficeSeg").querySelector('[data-s="casual"]').click()`);
  await new Promise(r => setTimeout(r, 20));
  check("the office style is its own setting", ls.getItem("oa.styleOffice") === "casual" && ev("state.style") === "casual");
  ev(`state.styleOffice="smart";`);

  console.log("\n--- 5. saved advice is for one kind of day -----------------------");
  ev(`state.officeDays=[${dow}]; dayKindOverride=null; state.city=""; state.place=""; closetComplete=false;
      fetch = async () => { throw new Error("offline"); };`);
  ls.setItem("oa.today", JSON.stringify({day: ev("todayISO()"), outfit: {base: "oxford shirt"}, outfit_text: "• Oxford shirt",
    picks: {base: "i1"}, closetUsed: true, weather: WX, occasion: "office", style: "smart"}));
  let r = await ev("getAdvice(40.3,-74.6)");
  check("the office advice is re-used on the office day", r.source === "saved", r.source);
  ev(`dayKindOverride={day:todayISO(),kind:"wfh"}`);
  r = await ev("getAdvice(40.3,-74.6)");
  check("…but not after switching to WFH", r.source !== "saved", r.source);
  ev(`dayKindOverride=null; state.styleOffice="casual"`);
  r = await ev("getAdvice(40.3,-74.6)");
  check("…nor after changing the office style", r.source !== "saved", r.source);
  ev(`state.styleOffice="smart"`);

  console.log("\n--- 6. the morning push reads the same keys ----------------------");
  const kt = fs.readFileSync(WORKER, "utf8");
  check("the worker sends the occasion and the kind's style",
    /val occasion = dayKind\(prefs\)/.test(kt) && /styleFor\(prefs, occasion\)/.test(kt)
    && /b\.put\("occasion", occasion\)/.test(kt));
  check("…from the app's keys and defaults",
    /"oa\.dayKind"/.test(kt) && /"oa\.officeDays"/.test(kt) && /"oa\.styleOffice", "smart"/.test(kt)
    && /DAY_OF_WEEK\) - 1/.test(kt) && /dow == 0 \|\| dow == 6 -> "off"/.test(kt));
  check("…and its saved copy says what was SENT, not re-read after the answer",
    /persistToday\(prefs, advice, requestedAt, occasion, style\)/.test(kt)
    && /\.put\("occasion", occasion\)\s*\.put\("style", style\)/.test(kt) && !/\.put\("occasion", dayKind/.test(kt));

  console.log("\n--- 7. restoring and resuming (pre-push reviewer, 2026-10-12) -----");
  ev(`state.officeDays=[${dow}]; dayKindOverride=null;`);
  ls.setItem("oa.today", JSON.stringify({day: ev("todayISO()"), outfit: {base: "oxford shirt"}, outfit_text: "• Oxford shirt",
    picks: {base: "i1"}, closetUsed: true, weather: WX, occasion: "office", style: "smart"}));
  check("office advice is restored on an office day", await ev("loadToday()") === true);
  ev(`dayKindOverride={day:todayISO(),kind:"wfh"}`);
  check("…but not under WFH", await ev("loadToday()") === false);
  ev(`dayKindOverride=null; paintDay(); state.officeDays=[${(dow + 1) % 7}];`);
  w.document.dispatchEvent(new w.Event("visibilitychange"));
  check("coming back to the app repaints the kind of day",
    ev(`$("kindSeg").querySelector(".on").dataset.k`) === ev("dayKind()"), ev(`$("kindSeg").querySelector(".on")?.dataset.k`));

  console.log("\n--- 8. switching while the first request is out (pre-push reviewer) --");
  const w3 = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w3.eval("appReady");
  w3.eval(`state.lat=40.3; state.lon=-74.6; state.officeDays=[${dow}]; dayKindOverride=null; lastRes=null; paintDay();
    window.__resolve=[]; window.__kinds=[];
    getAdvice = () => { window.__kinds.push(dayKind()); return new Promise(r => window.__resolve.push(r)); };`);
  const first = w3.eval("run()");
  await new Promise(r => setTimeout(r, 10));
  w3.eval(`$("kindSeg").querySelector('[data-k="wfh"]').click()`);
  await new Promise(r => setTimeout(r, 30));
  check("a change during the first request asks again, for the new kind",
    JSON.stringify(w3.eval("window.__kinds")) === '["office","wfh"]', w3.eval("window.__kinds"));
  const ans = s => ({weather: WX, outfit: {base: s}, text: `• ${s}`, source: "llm", picks: null});
  w3.eval(`window.__resolve[0](${JSON.stringify(ans("office pick"))})`); await first;
  w3.eval(`window.__resolve[1](${JSON.stringify(ans("wfh pick"))})`);
  await new Promise(r => setTimeout(r, 30));
  check("…and the WFH answer is the one shown", w3.eval("lastText") === "• wfh pick", w3.eval("lastText"));

  console.log("\n--- 9. only today's kind and style re-ask; stale advice leaves (pre-push reviewer) --");
  ev(`run=async()=>{window.__asked++;}; state.officeDays=[${(dow + 1) % 7}]; dayKindOverride=null;
      state.style="casual"; state.styleOffice="smart"; paintDay(); window.__asked=0;
      lastRes={weather:{},outfit:{base:"tee"},text:"• tee",occasion:scheduledKind(),style:"casual"};
      $("outfitCard").style.display="block";`);
  ev(`$("styleOfficeSeg").querySelector('[data-s="casual"]').click()`);
  await new Promise(r => setTimeout(r, 20));
  check("the office style edited on a non-office day does not re-ask", ev("window.__asked") === 0);
  ev(`$("officeDaysSeg").querySelector('[data-d="${(dow + 2) % 7}"]').click()`);
  await new Promise(r => setTimeout(r, 20));
  check("…nor does adding an office day that is not today", ev("window.__asked") === 0
    && ev(`$("outfitCard").style.display`) === "block");
  ev(`fetch = async () => { throw new Error("offline"); }; fetchWeatherLocal = async () => { throw new Error("offline"); };
      run = window.__realRun; state.lat=40.3; state.lon=-74.6;`);
  ev(`$("officeDaysSeg").querySelector('[data-d="${dow}"]').click()`);
  await new Promise(r => setTimeout(r, 60));
  check("making today an office day takes the home outfit off the screen, even offline",
    ev(`$("outfitCard").style.display`) === "none" && ev("lastText") === "", ev("lastText"));

  console.log("\n--- 10. seven days fit a narrow phone ----------------------------");
  check("the day buttons may shrink and carry no side padding",
    /#officeDaysSeg button\{padding:11px 0;min-width:0/.test(fs.readFileSync(HTML, "utf8")));

  console.log("\n--- 11. back and forth offline; overnight (pre-push reviewer) ----");
  const w4 = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w4.eval("appReady");
  const e4 = s => w4.eval(s);
  e4(`state.officeDays=[${dow}]; dayKindOverride=null; state.style="casual"; state.styleOffice="smart";
      state.lat=40.3; state.lon=-74.6; state.city=""; state.place="";
      fetch = async () => { throw new Error("offline"); }; fetchWeatherLocal = async () => { throw new Error("offline"); };`);
  w4.localStorage.setItem("oa.today", JSON.stringify({day: e4("todayISO()"), outfit: {base: "oxford shirt"},
    outfit_text: "• Oxford shirt", picks: {base: "i1"}, closetUsed: true, weather: WX, occasion: "office", style: "smart"}));
  await e4("loadToday()");
  e4(`$("kindSeg").querySelector('[data-k="wfh"]').click()`);
  await new Promise(r => setTimeout(r, 80));
  check("offline, WFH takes the office outfit down", e4(`$("outfitCard").style.display`) === "none");
  e4(`$("kindSeg").querySelector('[data-k="office"]').click()`);
  await new Promise(r => setTimeout(r, 80));
  check("…and back to Office shows the saved office advice again", e4("lastText") === "• Oxford shirt"
    && e4(`$("outfitCard").style.display`) !== "none", e4("lastText"));
  // Overnight: the page lives on, the schedule now says WFH, oa.today unchanged.
  e4(`state.officeDays=[${(dow + 1) % 7}]; window.__ran=0; run=async()=>{window.__ran++;};`);
  w4.document.dispatchEvent(new w4.Event("visibilitychange"));
  await new Promise(r => setTimeout(r, 80));
  check("resuming into another kind of day takes the old outfit down and asks",
    e4(`$("outfitCard").style.display`) === "none" && e4("window.__ran") >= 1, e4("window.__ran"));

  console.log("\n--- 12. resume keeps a matching request; restore checks the place --");
  const w5 = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w5.eval("appReady");
  w5.eval(`state.lat=40.3; state.lon=-74.6; state.officeDays=[${dow}]; dayKindOverride=null; lastRes=null;
    window.__n=0; getAdvice = () => { window.__n++; return new Promise(() => {}); };`);
  w5.eval("run()");
  await new Promise(r => setTimeout(r, 20));
  w5.document.dispatchEvent(new w5.Event("visibilitychange"));
  await new Promise(r => setTimeout(r, 40));
  check("an unchanged resume keeps the request already out", w5.eval("window.__n") === 1, w5.eval("window.__n"));
  w5.eval(`$("kindSeg").querySelector('[data-k="wfh"]').click()`);
  await new Promise(r => setTimeout(r, 40));
  check("…but a changed day still asks for the new one", w5.eval("window.__n") === 2, w5.eval("window.__n"));

  const w6 = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w6.eval("appReady");
  const e6 = s => w6.eval(s);
  e6(`state.officeDays=[${dow}]; dayKindOverride=null; state.style="casual"; state.styleOffice="smart";
      state.lat=25.8; state.lon=-80.2; state.city="Miami"; state.place="Miami";
      fetch = async () => { throw new Error("offline"); }; fetchWeatherLocal = async () => { throw new Error("offline"); };
      geocode = async () => ({lat:25.8, lon:-80.2, place:"Miami"});`);
  w6.localStorage.setItem("oa.today", JSON.stringify({day: e6("todayISO()"), outfit: {base: "wool coat"}, place: "Boston",
    outfit_text: "• Boston coat", picks: {base: "i1"}, closetUsed: true, weather: WX, occasion: "office", style: "smart"}));
  e6(`adviceWanted=true; lastRes={weather:{},outfit:{},text:"• miami wfh",occasion:"wfh",style:"casual"};
      dayKindOverride={day:todayISO(),kind:"wfh"}; paintDay();`);
  e6(`$("kindSeg").querySelector('[data-k="office"]').click()`);
  await new Promise(r => setTimeout(r, 120));
  check("another city's saved advice is not restored", e6("lastText") !== "• Boston coat", e6("lastText"));

  console.log("\n--- 13. resume reads the morning push first (pre-push reviewer) ---");
  const w7 = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w7.eval("appReady");
  // Yesterday's office advice on screen; overnight the schedule says WFH and the
  // morning push saved WFH advice.
  w7.eval(`state.lat=40.3; state.lon=-74.6; state.officeDays=[${(dow + 1) % 7}]; dayKindOverride=null; state.style="casual"; state.styleOffice="smart";
    lastRes={weather:{},outfit:{},text:"• office",occasion:"office",style:"smart"}; adviceWanted=true;
    window.__n=0; getAdvice = () => { window.__n++; return new Promise(() => {}); };`);
  w7.localStorage.setItem("oa.today", JSON.stringify({day: w7.eval("todayISO()"), outfit: {base: "grey tee"},
    outfit_text: "• WFH push", picks: {base: "i1"}, closetUsed: true, weather: WX,
    occasion: w7.eval("scheduledKind()"), style: "casual", how: "push"}));
  w7.document.dispatchEvent(new w7.Event("visibilitychange"));
  await new Promise(r => setTimeout(r, 120));
  check("the push's advice for today is shown", w7.eval("lastText") === "• WFH push", w7.eval("lastText"));
  check("…and nothing new is asked for", w7.eval("window.__n") === 0, w7.eval("window.__n"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
