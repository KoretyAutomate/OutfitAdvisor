/**
 * daily_use.test.js — the silent failures from the pre-launch review (2026-09-06).
 *
 * The app kept working through every one of these; what it told the wearer was
 * wrong or missing. Pinned here:
 *   - fetchT() gives up at its deadline (six calls had none, and the calendar scan
 *     awaits a triage per event, so one hung request spun it for good);
 *   - the source badge does not call the server's own fallbacks "AI";
 *   - a packing body of the wrong shape ends on an error line, not the spinner;
 *   - fully offline, the wearer reads a sentence, not "Failed to fetch".
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * Run: npm test   (or: node tests/daily_use.test.js)
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

const OUTFIT = {inner:"", base:"navy tee", mid:"", outer:"", bottoms:"chinos",
  footwear:"sneakers", accessories:"", tip:"nice day"};

(async () => {
  console.log("\n--- 1. a deadline on every fetch --------------------------------");
  const w = page();
  await w.eval("appReady");
  // A server that never answers: resolves only when the caller gives up.
  w.fetch = (url, opts) => new Promise((_, rej) => {
    opts.signal.addEventListener("abort", () => {
      const e = new Error("aborted"); e.name = "AbortError"; rej(e);
    });
  });
  let caught = null;
  try { await w.eval("fetchT(30, 'https://x/never', {method:'POST'})"); }
  catch (e) { caught = e; }
  check("fetchT rejects when the deadline passes", caught && caught.name === "AbortError",
    caught && caught.name);
  const src = fs.readFileSync(HTML, "utf8").split("\n");
  // A call may put its options on the next lines; judge the call by its first five.
  const bare = src.filter((l, i) => /await fetch\(/.test(l)
    && !/signal:ctl\.signal|fetchT/.test(src.slice(i, i + 5).join(" "))).length;
  check("no fetch is left without a signal or fetchT", bare === 0, bare);

  console.log("\n--- 2. what the wearer reads when there is no network -----------");
  check("the browser's words become a sentence",
    w.eval(`friendly(new TypeError("Failed to fetch"))`) === "No connection — check the network and try again.");
  check("a deadline reads the same way",
    w.eval(`friendly(Object.assign(new Error("x"),{name:"AbortError"}))`) === "No connection — check the network and try again.");
  check("an error that already says something keeps its words",
    w.eval(`friendly(new Error('Couldn\\'t find "Atlantis".'))`) === `Couldn't find "Atlantis".`);
  w.fetch = async () => { throw new TypeError("Failed to fetch"); };
  w.eval(`state.lat=40.7; state.lon=-74.0; state.city=""`);
  await w.eval("run()");
  await drain();
  const errText = w.document.getElementById("err").textContent;
  check("run() offline shows the sentence", /No connection/.test(errText), errText);
  check("and never the raw browser error", !/Failed to fetch|TypeError/.test(errText), errText);

  console.log("\n--- 3. the badge says who answered --------------------------------");
  const badge = (src, res) => {
    w.eval(`renderOutfit(${JSON.stringify(OUTFIT)},"words",${JSON.stringify(src)},${JSON.stringify(res)})`);
    const b = w.document.getElementById("srcBadge");
    return {text: b.textContent, off: b.className.includes("off"), src: b.className.includes("src")};
  };
  let b = badge("llm", {closetUsed:false, closetSent:false});
  check("the model's own answer is AI", b.text === "AI · 122B" && b.src, b);
  b = badge("rule-engine", {closetUsed:false, closetSent:true});
  check("the server's catalogue fallback is not AI", b.text === "estimate — AI unavailable" && b.off, b);
  b = badge("none", {closetUsed:false, closetSent:true});
  check("the closet-only refusal is not 'generic advice'", b.text === "advisor couldn't answer" && b.off, b);
  b = badge("llm", {closetUsed:true, closetSent:true});
  check("a closet answer is still credited", b.text === "AI · your closet" && b.src, b);

  console.log("\n--- 4. a packing answer of the wrong shape ------------------------");
  w.fetch = async () => ({ok:true, status:200, json: async () => ({})});
  const day = n => new Date(Date.now()+n*86400000).toISOString().slice(0,10);
  const trip = {id:"t1", place:"Osaka", start:day(1), end:day(3),
    type:"leisure", lat:34.7, lon:135.5, styles:["casual"]};
  await w.eval(`openPacking(${JSON.stringify(trip)})`);
  await drain();
  const pkErr = w.document.getElementById("pkErr").textContent;
  const pkText = w.document.getElementById("pkText").textContent;
  check("the sheet ends on an error line", /couldn't be read/.test(pkErr), pkErr);
  check("and the spinner is gone", !/Working out/.test(pkText), pkText);

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
