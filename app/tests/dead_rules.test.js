/**
 * dead_rules.test.js — a stored rule that can never fire (user, 2026-09-05).
 *
 *   "I don't know how many times I have to update no inner with white Crew-neck
 *    T-shirt. this is being ignored."
 *
 * Six times, by the server journal. The parser turned that sentence into a pair
 * whose two sides BOTH named the inner slot — every field legal, the restatement
 * word-perfect, and no outfit in the world able to make it fire. The server
 * refuses that shape now, but a phone that collected six of them before today
 * still has them, and in the list they look exactly like rules that work.
 *
 * So this covers the phone's half: spotting a ghost, and reading the original
 * sentence again rather than making the wearer retype it.
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * Run: npm test   (or: node tests/dead_rules.test.js)
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

const page = () => {
  const dom = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  });
  return dom.window;
};

/* Verbatim from POST /rule for the wearer's own words, before the fix. */
const GHOST = {kind:"avoid_pair", a:{type:"t_shirt", role:"inner", color:"white"},
  b:{role:"inner"}, restated:"Do not wear an inner layer with a white crew-neck t-shirt.",
  text:"no inner with white Crew-neck T-shirt", id:"rl-ghost"};
/* What the same sentence parses to now. */
const REAL = {kind:"avoid_pair", a:{type:"undershirt", role:"inner"},
  b:{type:"t_shirt", role:"base", color:"white"},
  restated:"No undershirt under the white t-shirt.",
  text:"no inner with white Crew-neck T-shirt", id:"rl-real"};

(async () => {
  const w = page();
  await w.eval("appReady");
  const dead = (r) => w.eval(`ruleIsDead(${JSON.stringify(r)})`);

  console.log("\n--- 1. which rules are ghosts -----------------------------------");
  check("both sides naming the same slot can never fire", dead(GHOST) === true);
  check("a pair with only one side cannot fire either",
    dead({kind:"avoid_pair", a:{role:"inner"}, b:null}) === true);
  check("the same sentence parsed properly is fine", dead(REAL) === false);
  check("one side naming a slot is fine",
    dead({kind:"avoid_pair", a:{role:"inner"}, b:{type:"t_shirt"}}) === false);
  check("neither side naming a slot is fine",
    dead({kind:"avoid_pair", a:{type:"undershirt"}, b:{type:"t_shirt"}}) === false);
  check("a same-colour rule gets the same treatment",
    dead({kind:"avoid_same_color", a:{role:"base"}, b:{role:"base"}}) === true);
  check("an outright ban has no pair to be skipped",
    dead({kind:"avoid_item", a:{role:"inner", type:"undershirt"}}) === false);

  console.log("\n--- 2. the list says which one is doing nothing -----------------");
  await w.eval(`userRules=[${JSON.stringify(GHOST)},${JSON.stringify(REAL)}]; renderRules()`);
  const rows = [...w.document.getElementById("rlList").children];
  check("both rules are listed", rows.length === 2, rows.length);
  check("the ghost is marked", /⚠️/.test(rows[0].textContent), rows[0].textContent);
  check("and says plainly that it was never applied",
    /never being\s+applied/.test(rows[0].textContent), rows[0].textContent);
  check("the working rule is not marked", !/⚠️/.test(rows[1].textContent));
  check("only the ghost offers a Fix",
    rows[0].querySelector("[data-rlfix]") !== null &&
    rows[1].querySelector("[data-rlfix]") === null);
  check("both can still be removed",
    rows.every(r => r.querySelector("[data-rlrm]") !== null));

  console.log("\n--- 3. Fix reads the original sentence again --------------------");
  let sent = null;
  w.fetch = async (url, opts) => {
    if (String(url).endsWith("/rule")) {
      sent = JSON.parse(opts.body);
      return {ok:true, status:200, json: async () => ({...REAL, id:undefined})};
    }
    return {ok:true, status:200, json: async () => ({})};
  };
  await w.eval(`document.querySelector("[data-rlfix]").click()`);
  await new Promise(r => setTimeout(r, 60));
  check("the wearer's own words were re-sent, not retyped",
    sent && sent.text === "no inner with white Crew-neck T-shirt", sent);
  const fixed = w.eval("JSON.stringify(userRules[0])");
  check("the entry is replaced by one that works",
    w.eval("ruleIsDead(userRules[0])") === false, fixed);
  check("the original sentence is kept with it",
    JSON.parse(fixed).text === "no inner with white Crew-neck T-shirt", fixed);
  check("and the id is kept, so nothing pointing at it is orphaned",
    JSON.parse(fixed).id === "rl-ghost", fixed);
  check("it is written down, not only held in memory",
    !/"role":"inner","color":"white"/.test(w.localStorage.getItem("oa.rules") || ""),
    w.localStorage.getItem("oa.rules"));
  check("the list stops warning about it",
    !/⚠️/.test(w.document.getElementById("rlList").children[0].textContent));

  console.log("\n--- 4. removed while the answer was in flight --------------------");
  /* Remove stays live while /rule is being asked, so by the time the answer lands
     the index this started with may point at a DIFFERENT rule — or past the end,
     which appends and resurrects the one just deleted. Raised by the pre-push
     reviewer, 2026-09-05. */
  const wR = page();
  await wR.eval("appReady");
  const OTHER = {kind:"avoid_item", a:{type:"jeans"}, restated:"No jeans.",
    text:"no jeans", id:"rl-other"};
  await wR.eval(`userRules=[${JSON.stringify(GHOST)},${JSON.stringify(OTHER)}]; renderRules()`);
  let release;
  wR.fetch = async () => {
    await new Promise(r => { release = r; });
    return {ok:true, status:200, json: async () => ({...REAL, id:undefined})};
  };
  const inFlight = wR.eval(`refreshRule(0)`);
  await new Promise(r => setTimeout(r, 10));
  // The wearer removes the ghost themselves while the request is out.
  await wR.eval(`userRules.splice(0,1); saveRules()`);
  release();
  await inFlight;
  await new Promise(r => setTimeout(r, 20));
  check("the rule they removed is not resurrected",
    wR.eval("userRules.length") === 1, wR.eval("JSON.stringify(userRules)"));
  check("and the surviving rule is untouched, not overwritten",
    wR.eval("userRules[0].id") === "rl-other", wR.eval("JSON.stringify(userRules)"));

  console.log("\n--- 5. a sentence that still cannot be parsed says so -----------");
  const w2 = page();
  await w2.eval("appReady");
  await w2.eval(`userRules=[${JSON.stringify(GHOST)}]; renderRules()`);
  w2.fetch = async () => ({ok:false, status:422, json: async () => ({})});
  await w2.eval(`document.querySelector("[data-rlfix]").click()`);
  await new Promise(r => setTimeout(r, 60));
  check("the wearer is told, rather than left with a silent ghost",
    /couldn't turn that into a rule/i.test(w2.document.getElementById("rlErr").textContent),
    w2.document.getElementById("rlErr").textContent);
  check("and the ghost is still there to remove by hand",
    w2.eval("userRules.length") === 1);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
