/**
 * laundry_from_outfit.test.js — "Some of these are in the laundry", on the outfit
 * card (user, 2026-10-16: "I want to make it possible to mark the items which are
 * still in laundry. today I had three recommended items still in laundry").
 *
 * Pinned:
 *   - the button shows for a closet answer, not for generic advice;
 *   - the sheet lists today's picks only, none ticked;
 *   - Save puts EVERY copy of a ticked garment in the laundry, and nothing else;
 *   - it re-plans at once, without the ticked ids in the closet sent and without
 *     `shown` (the rest of the card was fine), and a later re-roll sends `shown` again;
 *   - the Closet tab's sheet sees the same marks;
 *   - nothing ticked: no marks, no request.
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
const item = (id, label, category, extra = {}) => ({id, label, category, group: category === "bottoms" ? "bottoms" : "tops",
  type: category === "bottoms" ? "chinos" : "t_shirt", roles: [category], colors: ["navy"], warmth: 2,
  formality: ["casual"], waterproof: false, count: 1, ...extra});
const CLOSET = [
  item("tee", "navy tee", "base", {count: 2}),
  item("tee2", "white tee", "base"),
  item("cardi", "grey cardigan", "mid", {group: "tops", type: "cardigan", warmth: 3}),
  item("chino", "beige chinos", "bottoms"),
  item("jeans", "dark jeans", "bottoms"),
];
const OUTFIT = {inner:"", base:"navy tee", mid:"grey cardigan", outer:"", bottoms:"beige chinos",
  footwear:"", accessories:"", tip:""};
const PICKS = {inner:null, base:"tee", mid:"cardi", outer:null, bottoms:"chino", footwear:null, accessories:null};
const answer = picks => ({weather:WX, outfit:OUTFIT, outfit_text:"x", source:"llm",
  picks, closetUsed:true, missing:[]});

function capture(w, next) {
  const sent = [];
  w.fetch = async (url, opts) => {
    if (String(url).endsWith("/advice")) {
      sent.push(JSON.parse(opts.body));
      return {ok:true, status:200, json: async () => next()};
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
  const boxes = () => [...w.document.querySelectorAll("#inWashList input[data-id]")];
  const box = id => w.document.querySelector(`#inWashList input[data-id="${id}"]`);

  await ev(`closet=${JSON.stringify(CLOSET)}; wearLog=[]; lastWorn={}; saveCloset()`);
  ev(`state.lat=40.7; state.lon=-74.0; state.city=""`);
  let replies = [answer(PICKS)];
  const sent = capture(w, () => replies.shift() || answer(PICKS));

  console.log("\n--- 1. generic advice: nothing of theirs to mark ------------------");
  ev(`renderOutfit(${JSON.stringify(OUTFIT)},"x","llm",{picks:null,closetUsed:false})`);
  check("no button for generic advice", $("dLaundry").style.display === "none");

  console.log("\n--- 2. a closet answer offers it, listing only today's picks -------");
  await ev("run()"); await drain();
  check("one request so far", sent.length === 1, sent.length);
  check("the button shows", $("dLaundry").style.display === "");
  $("dLaundry").onclick(); await drain();
  check("the sheet opens", $("inWashWrap").classList.contains("show"));
  check("it lists exactly the three picks",
    JSON.stringify(boxes().map(b => b.dataset.id).sort()) === JSON.stringify(["cardi", "chino", "tee"]),
    boxes().map(b => b.dataset.id));
  check("nothing starts ticked", boxes().every(b => !b.checked));

  console.log("\n--- 3. nothing ticked: no marks, no request ------------------------");
  await $("inWashSave").onclick(); await drain();
  check("the sheet closes", !$("inWashWrap").classList.contains("show"));
  check("no wear was logged", ev("wearLog.length") === 0, ev("JSON.stringify(wearLog)"));
  check("no new request", sent.length === 1, sent.length);

  console.log("\n--- 4. two ticked: in the laundry, and a new outfit without them ---");
  replies = [answer({...PICKS, base:"tee2", mid:null, bottoms:"jeans"})];
  $("dLaundry").onclick(); await drain();
  box("tee").checked = true; box("chino").checked = true;
  await $("inWashSave").onclick(); await drain(); await drain();
  check("both copies of the navy tee are out", ev(`avail(closet.find(i=>i.id==="tee"))`) === 0);
  check("the chinos are out", ev(`avail(closet.find(i=>i.id==="chino"))`) === 0);
  check("the unticked cardigan is not", ev(`avail(closet.find(i=>i.id==="cardi"))`) === 1);
  check("marked by hand, not as worn",
    JSON.parse(ev("JSON.stringify(wearLog)")).every(x => x.marked === true), ev("JSON.stringify(wearLog)"));
  check("it re-planned at once", sent.length === 2, sent.length);
  const ids = (sent[1] && sent[1].closet || []).map(i => i.id);
  check("the ticked garments were not sent", !ids.includes("tee") && !ids.includes("chino"), ids);
  check("the rest of the wardrobe was", ids.includes("cardi") && ids.includes("tee2") && ids.includes("jeans"), ids);
  check("and it did not ask to move away from the whole card", sent[1] && !("shown" in sent[1]),
    sent[1] && Object.keys(sent[1]));
  check("the card shows the new outfit's picks", ev("JSON.stringify(lastPickIds.sort())") ===
    JSON.stringify(["jeans", "tee2"]), ev("JSON.stringify(lastPickIds)"));

  console.log("\n--- 5. afterwards a normal re-roll differs from the card again ----");
  await ev("run()"); await drain();
  check("a third request", sent.length === 3, sent.length);
  check("carrying `shown` as usual", sent[2] && sent[2].shown && sent[2].shown.base === "tee2",
    sent[2] && sent[2].shown);

  console.log("\n--- 6. the Closet tab's sheet sees the same marks ------------------");
  $("dirtyBtn").onclick(); await drain();
  const dirty = id => w.document.querySelector(`#dirtyList [data-id="${id}"]`);
  check("the chinos are ticked there",
    !!w.document.querySelector('#dirtyList input[data-id="chino"]:checked'));
  check("the navy tee's stepper says 2", dirty("tee") && dirty("tee").querySelector("b") &&
    dirty("tee").querySelector("b").textContent === "2");

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
