/** cold_gap.test.js — the server's "warmth" gap (nothing owned is warm enough for the
 * morning): excused by a warm layer of any role left in the wash, filed for the
 * shopping list under `outer`, cleared when one is bought — and nothing else about
 * genuine `outer` gaps changes. Loads the REAL app/www/index.html. Run: npm test */
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
  const ev = s => w.eval(s);
  ev(`closet=${JSON.stringify([it("tee", "base", 1), it("cardi", "mid", 4)])}`);
  const run = (m, sent) => JSON.stringify(ev(`ownershipGaps(${JSON.stringify(m)},3,${JSON.stringify(sent)})`));
  check("a warm cardigan in the wash excuses the warmth gap", run(["warmth"], ["tee"]) === "[]");
  check("sent and still nothing warm: the gap stands", run(["warmth"], ["tee", "cardi"]) === '["warmth"]');
  check("…and a plain missing raincoat is NOT excused by that cardigan", run(["outer"], ["tee"]) === '["outer"]');
  ev(`closetComplete=true; gaps=[]`);
  await ev(`recordGaps(["warmth"],{lo:1,hi:6},3,"${ev("todayISO()")}",["tee","cardi"])`);
  check("it is filed under outer, marked cold",
    ev(`gaps.length===1&&gaps[0].slot==="outer"&&gaps[0].cold===true`), ev("JSON.stringify(gaps)"));
  await ev(`clearGapsFilledBy(${JSON.stringify(it("sw", "mid", 1))})`);
  check("a thin layer does not clear it", ev("gaps.length") === 1);
  await ev(`clearGapsFilledBy(${JSON.stringify(it("sw2", "mid", 4))})`);
  check("a warm mid layer clears it", ev("gaps.length") === 0);
  ev(`gaps=[{slot:"outer",day:"${ev("todayISO()")}",lo:1,hi:6,at:3}]`);
  await ev(`clearGapsFilledBy(${JSON.stringify(it("sw3", "mid", 4))})`);
  check("a genuine outer gap is not cleared by a mid layer", ev("gaps.length") === 1);
  ev(`closet=${JSON.stringify([it("tee", "base", 1), it("parka", "outer", 5)])}`);
  const heavy = JSON.stringify(ev(`ownershipGaps(["warmth"],14,["tee"])`));
  check("(at 14C) a warmth-5 parka in the wash does not excuse it", heavy === '["warmth"]', heavy);
  ev(`closet=${JSON.stringify([it("tee", "base", 1)])}; closetComplete=true; gaps=[]`);
  await ev(`recordGaps(["outer","warmth"],{lo:1,hi:6},3,"${ev("todayISO()")}",["tee"])`);
  check("a genuine outer gap and a cold one the same day are both kept", ev("gaps.length") === 2);
  check("…but count as one short morning", ev("gapSummary()[0].n") === 1, ev("JSON.stringify(gapSummary())"));
  ev(`gaps=[{slot:"outer",cold:true,day:"${ev("todayISO()")}",lo:1,hi:30,at:3}]`);
  await ev(`clearGapsFilledBy(${JSON.stringify(it("sw5", "base", 4))})`);
  check("a heavy base layer all day is wrong for a 30C afternoon: it does not clear the gap", ev("gaps.length") === 1);
  check("pyjamas in the wash excuse nothing", JSON.stringify(ev(`(closet=[${JSON.stringify(it("tee", "base", 1))},${JSON.stringify({...it("pj", "inner", 3), type: "sleepwear"})}],
    ownershipGaps(["warmth"],3,["tee"]))`)) === '["warmth"]');
  ev(`closet=[${JSON.stringify(it("tee", "base", 1))}]; gaps=[]`);
  await ev(`recordGaps(["warmth"],{lo:1,hi:16},3,"${ev("todayISO()")}",["tee"],20)`);
  check("the server's calibrated afternoon figure is kept", ev("gaps[0].pk") === 20, ev("JSON.stringify(gaps)"));
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
