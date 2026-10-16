/**
 * didnt_wear.test.js — "I didn't wear this, and why" (user, 2026-10-16, rebuilt from
 * August's keepscan).
 *
 * Pinned:
 *   - the button shows with today's advice, and hides once the suggestion is worn;
 *   - a blank reason is refused; a preset or free text is saved, free text winning;
 *   - one reason per day, replaceable; "I did wear it" clears it;
 *   - exclusive with the thermal row both ways: a skip takes back today's rating
 *     (offset restored), a rating clears today's skip;
 *   - a notification rating newer than the skip makes it dead without deleting it;
 *   - /advice carries `skipped`, newest last, at most five, closet or not.
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
const page = () => new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
}).window;
const drain = () => new Promise(r => setTimeout(r, 0));

const WX = {lo:12, hi:20, desc:"Clear", rain:0, wind:2, code:0, emoji:"☀️",
  swing:8, feelsLo:11, feelsHi:20, morning:13, midday:19, evening:16,
  isRain:false, isSnow:false, date:new Date().toISOString().slice(0,10)};
const item = (id, label, category) => ({id, label, category, group: category === "bottoms" ? "bottoms" : "tops",
  type: category === "bottoms" ? "chinos" : "t_shirt", roles: [category], colors: ["navy"], warmth: 2,
  formality: ["casual"], waterproof: false, count: 1});
const CLOSET = [item("tee", "navy tee", "base"), item("chino", "beige chinos", "bottoms")];
const OUTFIT = {inner:"", base:"navy tee", mid:"", outer:"", bottoms:"beige chinos",
  footwear:"", accessories:"", tip:""};
const PICKS = {inner:null, base:"tee", mid:null, outer:null, bottoms:"chino", footwear:null, accessories:null};
const answer = () => ({weather:WX, outfit:OUTFIT, outfit_text:"x", source:"llm",
  picks:PICKS, closetUsed:true, missing:[]});

function capture(w) {
  const sent = [];
  w.fetch = async (url, opts) => {
    if (String(url).endsWith("/advice")) {
      sent.push(JSON.parse(opts.body));
      return {ok:true, status:200, json: async () => answer()};
    }
    return {ok:true, status:200, json: async () => ({})};
  };
  return sent;
}

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const $ = id => w.document.getElementById(id);
  const preset = r => w.document.querySelector(`#skReasons button[data-sk="${r}"]`);
  const log = () => JSON.parse(ev("JSON.stringify(skipLog)"));
  const stored = async () => JSON.parse(await ev(`prefGet("oa.skipped","[]")`));

  await ev(`closet=${JSON.stringify(CLOSET)}; wearLog=[]; lastWorn={}; saveCloset()`);
  ev(`state.lat=40.7; state.lon=-74.0; state.city=""`);
  const sent = capture(w);

  console.log("\n--- 1. the button comes with today's advice ----------------------");
  check("hidden before any advice", $("fbSkip").style.display === "none");
  await ev("run()"); await drain();
  check("shown on the card", $("fbSkip").style.display === "");
  check("the first request carries no reasons", sent[0] && !("skipped" in sent[0]), sent[0] && Object.keys(sent[0]));

  console.log("\n--- 2. a blank reason is refused ----------------------------------");
  $("fbSkip").onclick(); await drain();
  check("the sheet opens", $("skipWrap").classList.contains("show"));
  check("no cold/warm presets (the offset already says that)",
    ![...w.document.querySelectorAll("#skReasons button")].some(b => /cold|warm/i.test(b.textContent)));
  await $("skSave").onclick(); await drain();
  check("still open, with an error", $("skipWrap").classList.contains("show") && $("skErr").textContent.length > 0);
  check("nothing saved", log().length === 0);

  console.log("\n--- 3. a rating, then a skip: the rating is taken back ------------");
  $("skipWrap").classList.remove("show");
  const off0 = ev("tempOffset");
  await $("fbRow").onclick({target: w.document.querySelector('#fbRow button[data-r="2"]')}); await drain();
  check("the rating moved the offset", ev("tempOffset") !== off0, ev("tempOffset"));
  $("fbSkip").onclick(); await drain();
  $("skReasons").onclick({target: preset("Too formal for my day")});
  check("the preset is marked", preset("Too formal for my day").classList.contains("on"));
  await $("skSave").onclick(); await drain();
  check("saved", log().length === 1 && log()[0].reason === "Too formal for my day", log());
  check("…and on disk", (await stored()).length === 1);
  check("today's rating is gone", ev("todaysRating()") === null);
  check("the offset is back where it started", ev("tempOffset") === off0, [ev("tempOffset"), off0]);
  check("the card says so", $("skipNote").style.display === "" && /Too formal/.test($("skipNote").textContent));

  console.log("\n--- 4. changing the reason replaces it; free text wins -----------");
  $("fbSkip").onclick(); await drain();
  check("reopens on the saved preset", preset("Too formal for my day").classList.contains("on"));
  check("with 'I did wear it' offered", $("skClear").style.display === "");
  $("skFree").value = "Dinner out, dressed up"; $("skFree").oninput();
  await $("skSave").onclick(); await drain();
  check("still one for today", log().length === 1, log());
  check("free text won", log()[0].reason === "Dinner out, dressed up", log());

  console.log("\n--- 5. the next request carries it -------------------------------");
  await ev("run()"); await drain();
  const last = sent[sent.length - 1];
  check("`skipped` is sent", JSON.stringify(last.skipped) === JSON.stringify(["Dinner out, dressed up"]), last.skipped);

  console.log("\n--- 6. rating after a skip clears the skip -----------------------");
  await $("fbRow").onclick({target: w.document.querySelector('#fbRow button[data-r="0"]')}); await drain();
  check("today's skip is gone", log().length === 0 && ev("todaysSkip()") === null, log());
  check("the rating stands", ev("todaysRating()") && ev("todaysRating().rating") === 0);

  console.log("\n--- 7. only the newest five, and dead ones are not sent ----------");
  const day = n => ev(`dayISO(Date.now()-${n}*86400000)`);
  const old = [7,6,5,4,3,2,1].map(n => ({at: Date.now() - n*86400000, day: day(n), reason: `r${n}`}));
  await ev(`skipLog=${JSON.stringify(old)}; feedback=[]; saveSkips()`);
  // A notification rating on day 2, given after that day's skip: it was worn after all.
  await ev(`feedback=[{at:Date.now()-2*86400000+60000,rating:0}]`);
  await ev("run()"); await drain();
  const s7 = sent[sent.length - 1].skipped;
  check("day 2's reason is dead and not sent", s7 && !s7.includes("r2"), s7);
  check("newest last, five at most", JSON.stringify(s7) === JSON.stringify(["r6","r5","r4","r3","r1"]), s7);
  check("the dead one is still on disk (one writer per key)", (await stored()).some(x => x.reason === "r2"));

  console.log("\n--- 8. 'I did wear it' clears today's ----------------------------");
  await ev(`feedback=[]; skipLog=[{at:Date.now(),day:todayISO(),reason:"Plans changed"}]; saveSkips(); renderFeedback()`);
  $("fbSkip").onclick(); await drain();
  await $("skClear").onclick(); await drain();
  check("cleared", ev("todaysSkip()") === null && !(await stored()).some(x => x.day === ev("todayISO()")));

  console.log("\n--- 9. wearing the suggestion hides it and kills today's --------");
  await ev(`skipLog=[{at:Date.now(),day:todayISO(),reason:"Plans changed"}]; saveSkips(); renderFeedback()`);
  check("visible before", $("fbSkip").style.display === "");
  await $("dWear").onclick(); await drain(); await drain();
  check("a wear is recorded", !!ev("wearRecord()"));
  check("the button hides", $("fbSkip").style.display === "none");
  check("today's skip is dead", ev("todaysSkip()") === null && ev("liveSkips().length") === 0);
  await drain();
  check("…and deleted, not just hidden, so it cannot come back tomorrow",
    !(await stored()).some(x => x.day === ev("todayISO()")), await stored());

  console.log("\n--- 10. generic advice still carries the reasons -----------------");
  const w2 = page(); await w2.eval("appReady");
  const sent2 = capture(w2);
  w2.eval(`state.lat=40.7; state.lon=-74.0; state.city=""`);
  await w2.eval(`closet=[]; skipLog=[{at:Date.now()-86400000,day:dayISO(Date.now()-86400000),reason:"Too casual for my day"}]`);
  await w2.eval("run()"); await drain();
  check("no closet, reasons sent", sent2[0] && !sent2[0].closet &&
    JSON.stringify(sent2[0].skipped) === JSON.stringify(["Too casual for my day"]), sent2[0]);

  console.log("\n--- 11. the notification's 'Wearing it', settled across midnight --");
  /* Pre-push reviewer, 2026-10-16: skip yesterday, tap "Wearing it" on yesterday's
     push afterwards, open the app today — the reason must not come back. */
  const w3 = page(); await w3.eval("appReady");
  const y = w3.eval("dayISO(Date.now()-86400000)"), yAt = Date.now() - 86400000;
  await w3.eval(`prefSet("oa.skipped",JSON.stringify([{at:${yAt},day:"${y}",reason:"Plans changed"},
    {at:${yAt - 86400000},day:dayISO(${yAt - 86400000}),reason:"Too casual for my day"}]))`);
  await w3.eval(`skipLog=[]`);   // a page that has not loaded oa.skipped yet
  await w3.eval(`prefSet("oa.nativeWore",JSON.stringify({day:"${y}",map:{base:"tee"},at:${yAt + 60000}}))`);
  await w3.eval("mergeNativeWears()");
  const left = JSON.parse(await w3.eval(`prefGet("oa.skipped","[]")`));
  check("yesterday's withdrawn reason is deleted", !left.some(x => x.day === y), left);
  check("the older day's reason is kept (no empty write)", left.length === 1 && left[0].reason === "Too casual for my day", left);

  /* Undo leaves oa.nativeWore in place, acknowledged: a skip saved after it stands. */
  const w4 = page(); await w4.eval("appReady");
  const t0 = Date.now();
  const raw = JSON.stringify({day: w4.eval("todayISO()"), map: {base: "tee"}, at: t0 - 3600000});
  await w4.eval(`prefSet("oa.nativeWore",${JSON.stringify(raw)}); prefSet("oa.nativeWoreSeen",${JSON.stringify(raw)}); nativeWoreSeen=${JSON.stringify(raw)}`);
  await w4.eval(`skipLog=[{at:${t0},day:todayISO(),reason:"Plans changed"}]; saveSkips()`);
  await w4.eval("mergeNativeWears()");
  check("an acknowledged (undone) wear does not cancel a newer skip",
    w4.eval("liveSkips().length") === 1 && JSON.parse(await w4.eval(`prefGet("oa.skipped","[]")`)).length === 1);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
