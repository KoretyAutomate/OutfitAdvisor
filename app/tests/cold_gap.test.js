/** cold_gap.test.js — an `outer` gap raised for a cold morning is excused by a warm
 * layer that was only in the wash. Loads the REAL app/www/index.html. Run: npm test */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
let failed = 0;
const check = (n, c, d = "") => { console.log(`[${c ? "PASS" : "FAIL"}] ${n}${c ? "" : " " + JSON.stringify(d)}`); if (!c) failed++; };
const it = (id, cat, warmth) => ({id, label: id, category: cat, group: "tops", type: null, roles: [cat],
  colors: ["navy"], warmth, formality: ["casual"], waterproof: false, count: 1});
(async () => {
  const w = new JSDOM(fs.readFileSync(path.join(__dirname, "..", "www", "index.html"), "utf8"),
    {runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true}).window;
  await w.eval("appReady");
  w.eval(`closet=${JSON.stringify([it("tee", "base", 1), it("cardi", "mid", 4)])}`);
  const run = sent => JSON.stringify(w.eval(`ownershipGaps(["outer"],3,${JSON.stringify(sent)})`));
  check("a warm cardigan left in the wash excuses the outer gap", run(["tee"]) === "[]", run(["tee"]));
  check("sent and still nothing warm: the gap stands", run(["tee", "cardi"]) === '["outer"]', run(["tee", "cardi"]));
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
