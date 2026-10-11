/**
 * recent_wear.test.js — the advisor is told what they wore lately (2026-10-11), so it
 * can avoid yesterday's outfit when something else of theirs suits as well.
 *
 * Pinned:
 *   - recentWorn() counts LOCAL calendar days, the latest wear of each garment, last week only;
 *   - /advice from the app carries `recent`;
 *   - the push snapshot carries `recentAt` (times), for the worker to count at 06:45.
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

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w.eval("appReady");
  const now = new Date(2026, 9, 11, 7, 0).getTime();
  const at = (d, h) => new Date(2026, 9, 11 - d, h, 0).getTime();
  w.eval(`wearLog=${JSON.stringify([
    {itemId: "a", wornAt: at(1, 23)},      // last night, late
    {itemId: "a", wornAt: at(4, 8)},       // older wear of the same garment
    {itemId: "b", wornAt: at(3, 8)},
    {itemId: "c", wornAt: at(9, 8)},       // beyond a week
  ])}`);
  const rec = w.eval(`recentWorn(${now})`);
  check("a wear late last night is yesterday", rec.a === 1, rec);
  check("three days ago is 3", rec.b === 3, rec);
  check("beyond a week is not sent", !("c" in rec), rec);

  const bodies = [];
  w.fetch = async (url, opts) => {
    bodies.push(JSON.parse(opts.body));
    return {ok: true, status: 200, json: async () => ({weather: {}, outfit: {}, outfit_text: "", source: "llm",
      missing: [], picks: null})};
  };
  w.eval(`wearLog=${JSON.stringify([{itemId: "a", wornAt: Date.now() - 86400000}])}`);
  await w.eval("getAdvice(40.3,-74.6)");
  check("/advice from the app carries recent", bodies[0] && bodies[0].recent && bodies[0].recent.a === 1,
    bodies[0] && bodies[0].recent);

  await w.eval("savePushPayload()");
  const payload = JSON.parse(await w.eval(`prefGet("oa.pushPayload","{}")`));
  check("the push snapshot carries recentAt as times", payload.recentAt && typeof payload.recentAt.a === "number",
    payload.recentAt);

  // Raised by the pre-push reviewer, 2026-10-11: the laundry prunes wearLog once a
  // garment is clean — the history must outlive that.
  w.eval(`wearLog=${JSON.stringify([{itemId: "z", wornAt: Date.now() - 86400000, washedAt: Date.now() - 3600000}])}`);
  w.eval("laundry.dryHours=0");
  await w.eval("saveCloset()");
  check("the wash cleared the laundry entry", w.eval("wearLog.length") === 0);
  check("…but yesterday's wear is still history", w.eval("recentWorn().z") === 1, w.eval("recentWorn()"));
  const kept = JSON.parse(await w.eval(`prefGet("oa.lastWorn","{}")`));
  check("…and it is saved", Array.isArray(kept.z) && kept.z.length === 1, kept);

  // Raised by the pre-push reviewer, 2026-10-11: an undo takes today's wear out of
  // the history, keeping an earlier one.
  w.eval(`lastWorn={}; wearLog=${JSON.stringify([{itemId: "u", wornAt: Date.now() - 2 * 86400000},
                                                 {itemId: "u", wornAt: Date.now() - 60000}])}`);
  await w.eval("saveCloset()");
  check("worn today", w.eval("recentWorn().u") === 0, w.eval("recentWorn()"));
  w.eval('unlogWearToday("u")'); await w.eval("saveCloset()");
  check("…undone: the earlier wear is what remains", w.eval("recentWorn().u") === 2, w.eval("recentWorn()"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
