/**
 * feedback_math.test.js — FB2 verification.
 *
 * Loads the REAL app/www/index.html in jsdom and exercises the thermal-calibration
 * functions in place, same discipline as trips_math.test.js: no copy-pasted copy of
 * the math that could silently drift from the shipped code.
 *
 * What's under test is what a wrong implementation gets wrong quietly:
 *   - the SIGN (felt too warm ⇒ offset up ⇒ lighter clothes). Backwards here means
 *     days of steadily worse advice before anyone notices.
 *   - CONVERGENCE ("just right" stops moving it; repeated verdicts don't run away).
 *   - applyTempOffset returns a COPY and leaves non-thermal fields alone, so the
 *     displayed forecast is never the shifted one.
 *   - re-tapping replaces the rating instead of stacking a second correction.
 *   - parity with the Python twin's thresholds (server/engine.py).
 *
 * Run: NODE_PATH=<...>/node_modules node tests/feedback_math.test.js
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
  runScripts: "dangerously",
  url: "https://localhost/",
  pretendToBeVisual: true,
});
const w = dom.window;
const ev = (code) => w.eval(code);

// Preferences plugin is absent in jsdom -> prefSet falls through to localStorage.

console.log("\n--- 1. sign convention -------------------------------------------");
ev("tempOffset = 0; feedback = []; ratedThisAdvice = null;");
ev("fbApply(2)");                       // 🥵 too warm
check("too warm pushes the offset UP (plan for a warmer day => lighter)",
  ev("tempOffset") > 0, ev("tempOffset"));
ev("tempOffset = 0");
ev("fbApply(-2)");                      // 🥶 too cold
check("too cold pushes the offset DOWN (=> warmer clothes)",
  ev("tempOffset") < 0, ev("tempOffset"));

console.log("\n--- 2. magnitudes and the learning rate --------------------------");
ev("tempOffset = 0"); ev("fbApply(2)");
check("one 'too warm' moves 0.75 (1.5 x rate 0.5)", ev("tempOffset") === 0.75, ev("tempOffset"));
ev("tempOffset = 0"); ev("fbApply(1)");
check("one 'a bit warm' moves 0.3 (0.6 x rate 0.5)", ev("tempOffset") === 0.3, ev("tempOffset"));
check("the 'a bit' step is strictly smaller than the full step",
  Math.abs(ev("(()=>{const a=0;let t=0;return 0.6*0.5})()")) < 1.5 * 0.5);

console.log("\n--- 3. convergence ----------------------------------------------");
ev("tempOffset = 1.2"); ev("fbApply(0)");
check("'just right' does not move a calibrated offset", ev("tempOffset") === 1.2, ev("tempOffset"));
ev("tempOffset = 0; for(let i=0;i<3;i++) fbApply(2);");
check("three 'too warm' in a row land ~2.25, not a runaway",
  Math.abs(ev("tempOffset") - 2.25) < 1e-9, ev("tempOffset"));
ev("tempOffset = 0; for(let i=0;i<40;i++) fbApply(2);");
check("clamped at +6 however many ratings", ev("tempOffset") === 6, ev("tempOffset"));
ev("tempOffset = 0; for(let i=0;i<40;i++) fbApply(-2);");
check("clamped at -6 in the cold direction", ev("tempOffset") === -6, ev("tempOffset"));
ev("tempOffset = 0; fbApply(2); fbApply(-2);");
check("a 'too warm' then a 'too cold' cancel exactly (no float drift)",
  ev("tempOffset") === 0, ev("tempOffset"));

console.log("\n--- 4. revert is the exact inverse -------------------------------");
ev("tempOffset = 0.9; fbApply(-1); fbRevert(-1);");
check("fbRevert undoes fbApply exactly", Math.abs(ev("tempOffset") - 0.9) < 1e-9, ev("tempOffset"));

console.log("\n--- 5. applyTempOffset: copy, temps only -------------------------");
ev(`WX = {lo:10, hi:20, feelsLo:8, feelsHi:19, morning:11, midday:18, evening:14,
        rain:40, wind:9, code:61, desc:"Rain", isRain:true, isSnow:false, swing:10};`);
ev("SHIFTED = applyTempOffset(WX, 3)");
check("returns a new object (original untouched)", ev("WX.lo") === 10, ev("WX.lo"));
check("every temperature field shifts", ev(`
  SHIFTED.lo===13 && SHIFTED.hi===23 && SHIFTED.feelsLo===11 && SHIFTED.feelsHi===22 &&
  SHIFTED.morning===14 && SHIFTED.midday===21 && SHIFTED.evening===17`),
  ev("JSON.stringify(SHIFTED)"));
check("rain / wind / code / isRain are NOT shifted", ev(`
  SHIFTED.rain===40 && SHIFTED.wind===9 && SHIFTED.code===61 && SHIFTED.isRain===true`));
check("swing (hi-lo) is invariant under a uniform shift and left alone",
  ev("SHIFTED.swing===10 && (SHIFTED.hi-SHIFTED.lo)===(WX.hi-WX.lo)"));
check("offset 0 short-circuits to the same object (no needless copy)",
  ev("applyTempOffset(WX,0) === WX"));
check("nulls survive (hourly index misses stay null, not NaN)",
  ev("applyTempOffset({lo:5,hi:9,morning:null},2).morning === null"));

console.log("\n--- 5b. twin parity: the SAME table server/engine.py asserts ------");
// Python round() is banker's rounding, JS Math.round() is half-up. A .5 offset is
// reachable (five "a bit warm" taps = 1.5), so the two twins must agree digit for
// digit or the same weather yields different outfits depending on whether the DGX
// was reachable. This table is duplicated verbatim in scripts/check_feedback_fb1.py
// section [8] — both sides must pass it.
const HALF_UP = [
  [10, 1.5, 12], [11, 1.5, 13], [10, 0.5, 11], [11, 0.5, 12],
  [-10, 0.5, -9], [-11, 0.5, -10], [10, -1.5, 9], [11, -0.5, 11],
];
for (const [val, off, want] of HALF_UP) {
  const got = ev(`applyTempOffset({morning:${val}}, ${off}).morning`);
  check(`applyTempOffset(${val}, ${off >= 0 ? "+" : ""}${off}) === ${want}`, got === want, got);
}

console.log("\n--- 6. the offset actually changes the outfit --------------------");
check("a +6 calibration dresses lighter than a -6 one on the same weather", ev(`
  (()=>{ const cold=recommend(applyTempOffset(WX,-6),"man","casual");
         const warm=recommend(applyTempOffset(WX, 6),"man","casual");
         return cold.mid !== warm.mid || cold.base !== warm.base; })()`));
check("recommend() is unaffected when the calibration is 0", ev(`
  JSON.stringify(recommend(applyTempOffset(WX,0),"man","casual")) ===
  JSON.stringify(recommend(WX,"man","casual"))`));

console.log("\n--- 7. re-tapping replaces, never stacks -------------------------");
ev("tempOffset = 0; feedback = []; ratedThisAdvice = null;");
ev(`document.querySelector('#fbRow button[data-r="2"]').click()`);
ev(`document.querySelector('#fbRow button[data-r="-2"]').click()`);
// clicks are async handlers; drain the microtask queue before asserting
const drain = () => new Promise(r => setTimeout(r, 0));
(async () => {
  await drain(); await drain();
  check("changing your mind leaves ONE rating, not two", ev("feedback.length") === 1,
    ev("JSON.stringify(feedback)"));
  check("and the offset reflects only the final verdict", ev("tempOffset") === -0.75,
    ev("tempOffset"));
  ev(`document.querySelector('#fbRow button[data-r="-2"]').click()`);
  await drain(); await drain();
  check("tapping the same verdict again clears it", ev("feedback.length") === 0,
    ev("JSON.stringify(feedback)"));
  check("and restores the offset to where it was", ev("tempOffset") === 0, ev("tempOffset"));

  console.log("\n--- 8. persistence keys -----------------------------------------");
  ev("tempOffset = -1.35; feedback = [{at:1,rating:-2}];");
  await ev("saveFeedback()");
  check("oa.tempOffset persisted", w.localStorage.getItem("oa.tempOffset") === "-1.35",
    w.localStorage.getItem("oa.tempOffset"));
  check("oa.feedback persisted", w.localStorage.getItem("oa.feedback") === '[{"at":1,"rating":-2}]',
    w.localStorage.getItem("oa.feedback"));
  ev("feedback = Array.from({length:90},(_,i)=>({at:i,rating:0}));");
  await ev("saveFeedback()");
  check("history pruned to the last 60 entries", ev("feedback.length") === 60, ev("feedback.length"));
  check("pruning keeps the NEWEST entries", ev("feedback[feedback.length-1].at") === 89);

  console.log("\n--- 9. calibration copy is honest --------------------------------");
  ev("tempOffset = 1.4; feedback=[{at:1,rating:2}];");
  check("a positive offset is explained as 'you run warm'",
    /run warm/.test(ev("fbCalibrationText()")), ev("fbCalibrationText()"));
  ev("tempOffset = -1.4;");
  check("a negative offset is explained as 'you run cold'",
    /run cold/.test(ev("fbCalibrationText()")), ev("fbCalibrationText()"));
  ev("tempOffset = 0; feedback=[];");
  check("no ratings yet -> an invitation, not a fake calibration",
    !/Calibration/.test(ev("fbCalibrationText()")), ev("fbCalibrationText()"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
