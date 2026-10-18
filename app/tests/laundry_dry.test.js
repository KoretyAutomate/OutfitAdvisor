/**
 * laundry_dry.test.js — "Laundry & drying done" (user, 2026-10-18: "Could you update
 * laundry done to laundry and drying done and make it possible to tell drying is also
 * done?").
 *
 * Pinned:
 *   - the button says "Laundry & drying done";
 *   - washed alone, a load is drying for the set hours, as before;
 *   - "They're dry too" brings a load straight back — what was waiting and what an
 *     earlier wash left drying — and offers loads that are only drying;
 *   - a load not ticked keeps drying;
 *   - undo puts each wear back as it was: drying from the wash before, or waiting.
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
const drain = () => new Promise(r => setTimeout(r, 0));
const H = 3600000, D = 24 * H;
const item = (id, label, colors) => ({id, label, category: "base", group: "tops", type: "t_shirt",
  roles: ["base"], colors, warmth: 1, formality: ["casual"], waterproof: false, count: 1});

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true}).window;
  await w.eval("appReady");
  const ev = s => w.eval(s);
  let T = w.Date.now();
  w.Date.now = () => T;
  const $ = id => w.document.getElementById(id);
  const lb = l => w.document.querySelector(`#washLoads input[data-load="${l}"]`);
  const row = l => lb(l).closest("label").textContent.replace(/\s+/g, " ");
  const av = id => ev(`avail(closet.find(i=>i.id==="${id}"))`);
  const drying = id => ev(`dryingWears("${id}")`);
  const open = async () => { $("laundryBtn").onclick(); await drain(); };
  const go = async () => { await $("washGo").onclick(); await drain(); };
  const tickDry = async on => { $("washDry").checked = on; $("washDry").onchange(); await drain(); };

  await ev(`laundry.dryHours=24;
    closet=[${JSON.stringify(item("w", "white tee", ["white"]))},${JSON.stringify(item("d", "navy tee", ["navy"]))}];
    wearLog=[{itemId:"w",wornAt:${T - 2 * D}},{itemId:"d",wornAt:${T - 2 * D}}]; lastWorn={}; lastWash=null;
    saveCloset()`);
  await drain();

  console.log("\n--- 1. the button --------------------------------------------------");
  check("it says Laundry & drying done", $("laundryBtn").textContent === "Laundry & drying done",
    $("laundryBtn").textContent);

  console.log("\n--- 2. washed, not yet dry: as before ------------------------------");
  await open();
  check("'They're dry too' starts unticked", !$("washDry").checked);
  check("the button says Washed", $("washGo").textContent === "Washed");
  await go();
  check("both are drying", drying("w") === 1 && drying("d") === 1 && av("w") === 0 && av("d") === 0);

  console.log("\n--- 3. dry later: a load that is only drying -----------------------");
  T += 2 * H;
  await open();
  check("each load says what is drying", row("white").includes("1 drying") && row("dark").includes("1 drying"),
    [row("white"), row("dark")]);
  check("…but cannot be picked until 'dry too'", lb("white").disabled && $("washGo").disabled);
  await tickDry(true);
  check("ticking 'dry too' offers and ticks them", !lb("white").disabled && lb("white").checked && lb("dark").checked);
  check("the button says Washed & dry", $("washGo").textContent === "Washed & dry" && !$("washGo").disabled);
  lb("dark").checked = false; lb("dark").onchange();
  await go();
  check("the whites are back in rotation now", av("w") === 1 && drying("w") === 0);
  check("the darks, not ticked, are still drying", av("d") === 0 && drying("d") === 1);
  check("the worn day is still in the history", ev(`(lastWorn.w||[]).length`) === 1, ev("JSON.stringify(lastWorn)"));

  console.log("\n--- 4. undo: back to drying, as it was -----------------------------");
  check("undo is offered", $("unwashBtn").style.display === "");
  await $("unwashBtn").onclick(); await drain();
  check("the whites are drying again", av("w") === 0 && drying("w") === 1);
  check("…from the first wash, not a new one",
    ev(`wearLog.find(x=>x.itemId==="w").washedAt`) === T - 2 * H, ev("JSON.stringify(wearLog)"));

  console.log("\n--- 5. washed and dry in one go, and its undo ----------------------");
  await ev(`wearLog=[{itemId:"w",wornAt:${T - D}}]; lastWash=null; saveCloset()`); await drain();
  await open(); await tickDry(true);
  check("a load waiting to be washed is offered", lb("white").checked && !lb("white").disabled);
  await go();
  check("washed and dry: back now", av("w") === 1 && drying("w") === 0);
  await $("unwashBtn").onclick(); await drain();
  check("undo puts it back to be washed, not drying", av("w") === 0 && drying("w") === 0,
    ev("JSON.stringify(wearLog)"));

  console.log("\n--- 6. after the drying time, nothing is held ---------------------");
  await ev(`wearLog=[{itemId:"d",wornAt:${T - 3 * D},washedAt:${T - 30 * H}}]; saveCloset()`); await drain();
  check("a wash dry by the clock needs no tick", av("d") === 1);

  console.log(`\nlaundry_dry: ${passed} passed, ${failed} failed`);
  if (failed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
