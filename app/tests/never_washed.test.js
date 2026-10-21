/**
 * never_washed.test.js — footwear and accessories never go in the laundry (user,
 * 2026-10-17: "Footware and accessories shouldn't have any laundry field"; asked:
 * they never enter the laundry at all, and socks — filed under Footwear — still do).
 *
 * Pinned:
 *   - a worn pair of shoes or a hat stays available; socks and a tee are held;
 *   - the wear still reaches the history, once per day, and an old hold clears;
 *   - the edit sheet shows no laundry field for them, and follows group/kind edits;
 *   - the laundry sheets, "Laundry done", the outfit card and the push skip them.
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
const D = 24 * 3600000;

const item = (id, label, group, type, category, extra = {}) => ({id, label, category, group, type,
  roles: [category], colors: ["black"], warmth: 1, formality: ["casual"], waterproof: false,
  count: 1, ...extra});
const CLOSET = [
  item("tee", "black tee", "tops", "t_shirt", "base"),
  item("shoe", "black sneakers", "footwear", "sneakers", "footwear"),
  item("sock", "black socks", "footwear", "socks", "footwear", {count: 3}),
  item("hat", "black cap", "accessories", "hat", "accessories"),
];

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const T = w.Date.now();
  w.Date.now = () => T;
  const $ = id => w.document.getElementById(id);
  const av = id => ev(`avail(closet.find(i=>i.id==="${id}"))`);
  const log = () => JSON.parse(ev("JSON.stringify(wearLog)"));
  const reset = async (wl = "[]") => {
    await ev(`closet=${JSON.stringify(CLOSET)}; wearLog=${wl}; lastWorn={}; saveCloset()`); await drain();
  };

  console.log("\n--- 1. the rule ----------------------------------------------------");
  check("sneakers are never washed", ev(`neverWashed(${JSON.stringify(CLOSET[1])})`) === true);
  check("a cap is never washed", ev(`neverWashed(${JSON.stringify(CLOSET[3])})`) === true);
  check("socks are", ev(`neverWashed(${JSON.stringify(CLOSET[2])})`) === false);
  check("a tee is", ev(`neverWashed(${JSON.stringify(CLOSET[0])})`) === false);
  check("a coat is never washed (2026-10-21)", ev(`neverWashed(${JSON.stringify(item("coat", "olive parka", "outerwear", "coat", "outer"))})`) === true);
  check("a cardigan worn as a layer still is", ev(`neverWashed(${JSON.stringify(item("cardi", "grey cardigan", "tops", "cardigan", "mid"))})`) === false);

  console.log("\n--- 2. a wear holds the tee and socks, not the shoes or the cap ----");
  await reset();
  for (const id of ["tee", "shoe", "sock", "hat"]) ev(`logWear("${id}")`);
  check("the tee is out", av("tee") === 0);
  check("one pair of socks is out", av("sock") === 2);
  check("the sneakers are still wearable", av("shoe") === 1);
  check("the cap is still wearable", av("hat") === 1);
  await ev("saveCloset()"); await drain();
  check("the save keeps only the washed garments' wears",
    JSON.stringify(log().map(x => x.itemId).sort()) === JSON.stringify(["sock", "tee"]), log());
  const hist = JSON.parse(ev("JSON.stringify(lastWorn)"));
  check("…but the shoes and the cap are in the wear history", (hist.shoe || []).length === 1
    && (hist.hat || []).length === 1, hist);
  w.Date.now = () => T + 60000;        // a minute later, the same day
  ev(`logWear("shoe")`); await ev("saveCloset()"); await drain();
  w.Date.now = () => T;
  check("a second wear the same day is not a second day",
    JSON.parse(ev("JSON.stringify(lastWorn)")).shoe.length === 1, ev("JSON.stringify(lastWorn)"));
  ev(`unlogWearToday("shoe")`);
  check("an undo still takes today's wear back", !JSON.parse(ev("JSON.stringify(lastWorn)")).shoe);
  ev(`logWear("shoe")`);
  check("…and it can be logged again", log().some(x => x.itemId === "shoe"));

  console.log("\n--- 3. a hold from before this build clears -----------------------");
  await reset(JSON.stringify([{itemId: "shoe", wornAt: T - D}, {itemId: "hat", wornAt: T - D, marked: true},
    {itemId: "tee", wornAt: T - D}]));
  check("yesterday's sneakers are back", av("shoe") === 1);
  check("a cap marked by hand is back", av("hat") === 1);
  check("yesterday's tee is not", av("tee") === 0);
  check("the stale holds are pruned", log().every(x => x.itemId === "tee"), log());
  check("the worn day is kept, the marked one is not",
    ev("JSON.stringify(Object.keys(lastWorn).sort())") === '["shoe","tee"]', ev("JSON.stringify(lastWorn)"));

  console.log("\n--- 4. the edit sheet ---------------------------------------------");
  ev(`laundry.splits=["colour","fabric","weight","soil"]`);
  const shown = id => $(id).style.display !== "none";
  const open = async id => { await ev(`openSheet(closet.find(i=>i.id==="${id}"),{isNew:false})`); await drain(); };
  await open("tee");
  check("a tee has its laundry fields", shown("shLoadBox") && shown("shFabricBox")
    && shown("shWeightBox") && shown("shSoilBox"));
  await open("shoe");
  check("sneakers have none", !shown("shLoadBox") && !shown("shFabricBox")
    && !shown("shWeightBox") && !shown("shSoilBox"));
  await open("hat");
  check("a cap has none", !shown("shLoadBox") && !shown("shFabricBox"));
  await open("sock");
  check("socks keep them", shown("shLoadBox") && shown("shFabricBox"));
  $("shType").value = "sneakers"; $("shType").dispatchEvent(new w.Event("change")); await drain(); await drain();
  check("changing the kind from socks to sneakers hides them", !shown("shLoadBox") && !shown("shFabricBox"));
  await open("tee");
  $("shGroup").value = "accessories"; $("shGroup").dispatchEvent(new w.Event("change")); await drain(); await drain();
  check("moving a garment into Accessories hides them", !shown("shLoadBox") && !shown("shSoilBox"));
  $("shGroup").value = "tops"; $("shGroup").dispatchEvent(new w.Event("change")); await drain(); await drain();
  check("…and moving it back shows them", shown("shLoadBox") && shown("shSoilBox"));
  ev("closeSheet()");
  ev(`laundry.splits=["colour"]`);

  console.log("\n--- 5. the laundry sheets -----------------------------------------");
  await reset();
  $("dirtyBtn").onclick(); await drain();
  const listed = [...w.document.querySelectorAll("#dirtyList [data-id]")].map(e => e.dataset.id);
  check("'What's still in the laundry?' lists the tee and the socks only",
    JSON.stringify([...new Set(listed)].sort()) === JSON.stringify(["sock", "tee"]), listed);
  $("dirtyCancel").onclick();
  await reset(JSON.stringify([{itemId: "shoe", wornAt: T - D}, {itemId: "tee", wornAt: T - D}]));
  ev(`wearLog.push({itemId:"shoe",wornAt:${T - D}})`);        // unpruned, as between saves
  const by = JSON.parse(ev("JSON.stringify(washable())"));
  const offered = Object.values(by).flat().map(x => x.itemId);
  check("'Laundry done' offers the tee, not the sneakers",
    offered.includes("tee") && !offered.includes("shoe"), offered);

  console.log("\n--- 5b. Settings → Laundry lists them in no load ----------------");
  await ev(`closet=${JSON.stringify(CLOSET.map(i => i.id === "tee" ? i : {...i, load: "dark"}))};
    wearLog=[]; lastWorn={}; saveCloset()`); await drain();
  const inLoads = [...w.document.querySelectorAll("#loadList select[data-item]")].map(e => e.dataset.item);
  check("the load lists show the tee and the socks only",
    JSON.stringify(inLoads.sort()) === JSON.stringify(["sock", "tee"]), inLoads);
  check("a hand-picked load on shoes is not counted",
    $("loadUnpin").textContent.startsWith("Let 1 hand-picked garment "), $("loadUnpin").textContent);
  await $("loadUnpin").onclick(); await drain();
  check("unpinning frees the socks and leaves the shoes' stored value alone",
    ev(`closet.find(i=>i.id==="sock").load`) === undefined && ev(`closet.find(i=>i.id==="shoe").load`) === "dark");

  console.log("\n--- 6. the outfit card --------------------------------------------");
  await reset();
  const O = {inner: "", base: "black tee", mid: "", outer: "", bottoms: "", footwear: "black sneakers",
    accessories: "black cap", tip: ""};
  const P = {inner: null, base: "tee", mid: null, outer: null, bottoms: null, footwear: "shoe", accessories: "hat"};
  ev(`renderOutfit(${JSON.stringify(O)},"x","llm",{picks:${JSON.stringify(P)},closetUsed:true})`);
  check("the laundry button shows for the tee", $("dLaundry").style.display === "");
  $("dLaundry").onclick(); await drain();
  const inWash = [...w.document.querySelectorAll("#inWashList input[data-id]")].map(b => b.dataset.id);
  check("it lists the tee alone", JSON.stringify(inWash) === '["tee"]', inWash);
  $("inWashCancel").onclick();
  ev(`renderOutfit(${JSON.stringify(O)},"x","llm",{picks:${JSON.stringify({...P, base: null})},closetUsed:true})`);
  check("no button when only shoes and a cap are picked", $("dLaundry").style.display === "none");

  console.log("\n--- 7. the morning push -------------------------------------------");
  await reset(JSON.stringify([{itemId: "shoe", wornAt: T - 1000}, {itemId: "tee", wornAt: T - 1000}]));
  const held = JSON.parse(ev("JSON.stringify([...heldUnits().keys()])"));
  check("only the tee is held in the push", JSON.stringify(held) === '["tee"]', held);
  const payload = JSON.parse(w.localStorage.getItem("oa.pushPayload") || "{}");
  const shoe = (payload.closet || []).find(i => i.id === "shoe");
  check("the sneakers go out available, with no free-at times",
    !!shoe && shoe.availableCount === 1 && !shoe.freeAt, shoe);

  console.log("\n--- 8. the notification's wear ------------------------------------");
  await reset();
  ev(`logWear("shoe")`); await ev("saveCloset()"); await drain();
  ev(`nativeSeen=new Set()`);
  w.localStorage.setItem("oa.nativeWears", JSON.stringify([{itemId: "shoe", wornAt: T - 500, key: "nShoe"}]));
  await ev("mergeNativeWears()"); await ev("saveCloset()"); await drain();
  check("a notification wear the app already has is not a second one",
    JSON.parse(ev("JSON.stringify(lastWorn)")).shoe.length === 1, ev("JSON.stringify(lastWorn)"));

  console.log("\n--- coats: worn yesterday, still there today (user, 2026-10-21) ---------");
  const parka = item("parka", "olive parka", "outerwear", "coat", "outer");
  await ev(`closet=${JSON.stringify([...CLOSET, parka])}; wearLog=[{itemId:"parka",wornAt:${T - D}}]; lastWorn={}; saveCloset()`);
  await drain();
  check("yesterday's coat is available today", av("parka") === 1);
  check("…and its wear is in the history", (JSON.parse(ev("JSON.stringify(lastWorn)")).parka || []).length === 1,
    ev("JSON.stringify(lastWorn)"));
  check("…and it is out of the laundry", !log().some(x => x.itemId === "parka"), log());

  console.log(`\nnever_washed: ${passed} passed, ${failed} failed`);
  if (failed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
