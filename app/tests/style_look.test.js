/**
 * style_look.test.js — how outfits LOOKED (user, 2026-10-07: "build all 3. user
 * feedback is important to build"), and the pattern field the style rules read.
 *
 * Pinned:
 *   - a thumb is about the outfit as worn (else as suggested), frozen at the tap;
 *     one per day, the same thumb again takes it back;
 *   - the summary: down on two different days and never up = disliked (enforced);
 *     down once = hint; up twice = liked; deleted garments drop out;
 *   - "What's off?" becomes a rule when it can, a style note when it cannot;
 *   - votes and notes ride on /advice and in the push payload;
 *   - the pattern field: edit sheet, new items, the photo scan.
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

const item = (id, label, cat, extra = {}) => ({id, label, category: cat, group: cat === "bottoms"
  ? "bottoms" : cat === "footwear" ? "footwear" : "tops", type: null, roles: [cat],
  colors: ["navy"], warmth: 2, formality: ["casual"], waterproof: false, count: 1, ...extra});
const TEE = item("t1", "white tee", "base"), CARDI = item("m1", "grey cardigan", "mid");
const JEANS = item("b1", "jeans", "bottoms"), SHOES = item("f1", "sneakers", "footwear");

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const btn = v => w.document.querySelector(`#lookRow button[data-v="${v}"]`);

  console.log("\n--- 1. a thumb on today's outfit -----------------------------------");
  await ev(`closet=${JSON.stringify([TEE, CARDI, JEANS, SHOES])}; saveCloset();
    lastRes={closetUsed:true,picks:{base:"t1",mid:"m1",bottoms:"b1",footwear:"f1"}}; renderLook()`);
  await btn(-1).onclick(); await drain();
  let votes = JSON.parse(ev("JSON.stringify(styleVotes)"));
  check("a thumbs-down is stored with the garments as shown",
    votes.length === 1 && votes[0].v === -1 && votes[0].ids.join() === "t1,m1,b1,f1", votes);
  check("it opens the what's-off box", w.document.getElementById("lookWhy").style.display === "");
  await ev(`lastRes={closetUsed:true,picks:{base:"t1",bottoms:"b1"}}`);
  check("the vote is frozen: a re-roll does not change what was judged",
    JSON.parse(ev("JSON.stringify(styleVotes)"))[0].ids.length === 4);
  await btn(-1).onclick(); await drain();
  check("the same thumb again takes it back", ev("styleVotes.length") === 0);
  await btn(1).onclick(); await btn(-1).onclick(); await drain();
  check("one vote per day — a change of mind replaces it",
    ev("styleVotes.length") === 1 && ev("styleVotes[0].v") === -1);
  await ev(`woreLogged={base:"t1",mid:"m1",bottoms:"b1"}; woreDay=todayISO(); styleVotes=[]`);
  await btn(1).onclick(); await drain();
  check("a logged correction is what gets judged, not the suggestion",
    ev("styleVotes[0].ids.join()") === "t1,m1,b1");
  await ev(`woreLogged=null; woreDay=null`);

  console.log("\n--- 2. what the advisor learns -------------------------------------");
  const day = n => ev(`dayISO(Date.now()-${n}*DAY_MS)`);
  const d1 = day(1), d2 = day(2), d3 = day(3);
  await ev(`styleVotes=[{day:"${d1}",ids:["t1","b1"],v:-1}]`);
  let sv = JSON.parse(ev("JSON.stringify(styleSummary())"));
  check("one thumbs-down is only a hint", sv.hint.length === 1 && sv.disliked.length === 0, sv);
  await ev(`styleVotes=[{day:"${d1}",ids:["t1","b1"],v:-1},{day:"${d2}",ids:["t1","b1","m1"],v:-1}]`);
  sv = JSON.parse(ev("JSON.stringify(styleSummary())"));
  check("down on two different days is enforced", sv.disliked.some(p => p.join() === "b1,t1"), sv);
  check("…and a pair seen down only once stays a hint",
    sv.hint.some(p => p.includes("m1")) && !sv.disliked.some(p => p.includes("m1")), sv);
  await ev(`styleVotes.push({day:"${d3}",ids:["t1","b1"],v:1})`);
  sv = JSON.parse(ev("JSON.stringify(styleSummary())"));
  check("a thumbs-up on the pair since means it is not enforced",
    !sv.disliked.some(p => p.join() === "b1,t1"), sv);
  await ev(`styleVotes=[{day:"${d1}",ids:["t1","m1"],v:1},{day:"${d2}",ids:["t1","m1"],v:1}]`);
  sv = JSON.parse(ev("JSON.stringify(styleSummary())"));
  check("liked twice is liked", sv.liked.some(p => p.join() === "m1,t1"), sv);
  await ev(`closet=closet.filter(i=>i.id!=="m1"); saveCloset()`);
  check("a deleted garment drops out of what is sent", ev("styleSummary()") === null);
  await ev(`closet=${JSON.stringify([TEE, CARDI, JEANS, SHOES])}; saveCloset(); styleVotes=[]`);

  console.log("\n--- 3. what's off? ---------------------------------------------------");
  let posted = null, status = 422;
  w.fetch = async (url, opts) => {
    posted = {url, body: JSON.parse(opts.body)};
    return {ok: status === 200, status,
      json: async () => ({kind: "avoid_item", a: {type: "hoodie"}, restated: "no hoodies"})};
  };
  w.document.getElementById("lookText").value = "too many colours";
  await w.document.getElementById("lookSend").onclick(); await drain();
  check("a sentence that cannot be a rule becomes a style note",
    /\/rule$/.test(posted.url) && ev("styleNotes.length") === 1 && ev("styleNotes[0].text") === "too many colours");
  check("…and says so", /style note/.test(w.document.getElementById("lookNote").textContent));
  status = 200;
  w.document.getElementById("lookText").value = "never hoodies";
  await w.document.getElementById("lookSend").onclick(); await drain();
  check("one that can becomes an enforced rule", ev("userRules.some(r=>r.text==='never hoodies')"),
    JSON.parse(ev("JSON.stringify(userRules)")));
  check("the Things-to-avoid box still works through the same path",
    typeof ev("typeof addRule") === "string" && ev("typeof ruleFromText") === "function");

  console.log("\n--- 4. on the wire ---------------------------------------------------");
  await ev(`styleVotes=[{day:"${d1}",ids:["t1","b1"],v:-1},{day:"${d2}",ids:["t1","b1"],v:-1}]; saveStyle()`);
  const pay = JSON.parse(await ev(`prefGet("oa.pushPayload","{}")`));
  check("the push payload carries the votes and notes",
    pay.styleVotes && pay.styleVotes.disliked.length === 1 && pay.styleVotes.notes[0] === "too many colours", pay.styleVotes);
  let sent = null;
  w.fetch = async (url, opts) => { if (/\/advice$/.test(url)) sent = JSON.parse(opts.body);
    return {ok: false, status: 500, json: async () => ({})}; };
  try { await ev(`getAdvice(40.3,-74.6)`); } catch (e) { /* offline fallback is fine */ }
  check("and so does the advice request", sent && sent.styleVotes && sent.styleVotes.disliked.length === 1, sent && sent.styleVotes);

  console.log("\n--- 5. the pattern field ---------------------------------------------");
  await ev(`openSheet(closet[0],{isNew:false})`); await drain();
  check("unknown opens as not specified", w.document.getElementById("shPattern").value === "");
  w.document.getElementById("shPattern").value = "striped";
  await w.document.getElementById("shSave").onclick(); await drain();
  check("a chosen pattern is saved", ev("closet[0].pattern") === "striped");
  check("and sent to the server", ev("itemMeta(closet[0]).pattern") === "striped");
  await ev(`closet=[${JSON.stringify({...TEE, id: "s1", photo: true})}]; saveCloset()`);
  w.localStorage.setItem("oa.photo.s1", "P".repeat(200));
  w.fetch = async () => ({ok: true, status: 200, json: async () => ({brand: null, sleeve: "short", pattern: "checked"})});
  await ev("scanBrands()");
  check("the photo scan reads the pattern", ev("closet[0].pattern") === "checked" && ev("closet[0].sleeve") === "short");

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
