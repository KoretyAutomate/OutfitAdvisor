/**
 * laundry_dry.test.js — "Laundry done", "Drying done", "Laundry & drying done"
 * (user, 2026-10-18: "needs to have laundry done, drying done, and laundry & drying
 * done. All three must have an option").
 *
 * Pinned:
 *   - the status sheet has all three buttons;
 *   - Laundry done: a load is washed and drying for the set hours, as before; a load
 *     that is only drying cannot be picked;
 *   - Drying done: offers the loads with something drying, brings them straight back,
 *     and never washes what is still waiting in the same load;
 *   - Laundry & drying done: what was waiting and what an earlier wash left drying
 *     come back now;
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
  const open = async (btn = "laundryBtn") => { $(btn).onclick(); await drain(); };
  const go = async () => { await $("washGo").onclick(); await drain(); };

  await ev(`laundry.dryHours=24;
    closet=[${JSON.stringify(item("w", "white tee", ["white"]))},${JSON.stringify(item("d", "navy tee", ["navy"]))}];
    wearLog=[{itemId:"w",wornAt:${T - 2 * D}},{itemId:"d",wornAt:${T - 2 * D}}]; lastWorn={}; lastWash=null;
    saveCloset()`);
  await drain();

  console.log("\n--- 1. three buttons -----------------------------------------------");
  check("Laundry done, Drying done, Laundry & drying done",
    $("laundryBtn").textContent === "Laundry done" && $("dryBtn").textContent === "Drying done"
      && $("washDryBtn").textContent === "Laundry & drying done",
    [$("laundryBtn").textContent, $("dryBtn").textContent, $("washDryBtn").textContent]);

  console.log("\n--- 2. washed, not yet dry: as before ------------------------------");
  await open();
  check("the button says Washed", $("washGo").textContent === "Washed");
  await go();
  check("both are drying", drying("w") === 1 && drying("d") === 1 && av("w") === 0 && av("d") === 0);

  console.log("\n--- 3. dry later: a load that is only drying -----------------------");
  T += 2 * H;
  await open();
  check("each load says what is drying", row("white").includes("1 drying") && row("dark").includes("1 drying"),
    [row("white"), row("dark")]);
  check("…but Laundry done cannot pick them", lb("white").disabled && $("washGo").disabled);
  $("washCancel").onclick();
  await open("dryBtn");
  check("Drying done offers and ticks them", !lb("white").disabled && lb("white").checked && lb("dark").checked);
  check("the button says Dry", $("washGo").textContent === "Dry" && !$("washGo").disabled);
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
  await open("dryBtn");
  check("Drying done does not offer a load that is only waiting to be washed", lb("white").disabled,
    row("white"));
  $("washCancel").onclick();
  await open("washDryBtn");
  check("Laundry & drying done offers it", $("washGo").textContent === "Washed & dry");
  check("a load waiting to be washed is offered", lb("white").checked && !lb("white").disabled);
  await go();
  check("washed and dry: back now", av("w") === 1 && drying("w") === 0);
  await $("unwashBtn").onclick(); await drain();
  check("undo puts it back to be washed, not drying", av("w") === 0 && drying("w") === 0,
    ev("JSON.stringify(wearLog)"));

  console.log("\n--- 5b. a load both dirty and drying --------------------------------");
  const mixed = `wearLog=[{itemId:"w",wornAt:${T - D}},{itemId:"w",wornAt:${T - 2 * D},washedAt:${T - H}}];
    closet[0].count=2; lastWash=null; saveCloset()`;
  const waiting = () => ev(`wearLog.filter(x=>x.itemId==="w"&&x.washedAt==null).length`);
  await ev(mixed); await drain();
  await open("dryBtn"); await go();
  check("Drying done dries the wet one", drying("w") === 0 && av("w") === 1, ev("JSON.stringify(wearLog)"));
  check("…and leaves the dirty one waiting", waiting() === 1, ev("JSON.stringify(wearLog)"));
  check("its undo says dry", $("unwashBtn").textContent.startsWith("Undo last dry — "), $("unwashBtn").textContent);
  await ev(mixed); await drain();
  await open("washDryBtn");
  lb("white").checked = false; lb("white").onchange();
  await go();
  check("unticked under Laundry & drying done: nothing of theirs was washed", waiting() === 1,
    ev("JSON.stringify(wearLog)"));
  $("washWrap").classList.remove("show");
  await ev(mixed); await drain();
  await open("washDryBtn"); await go();
  check("ticked: both back in rotation", av("w") === 2 && waiting() === 0, ev("JSON.stringify(wearLog)"));
  await ev(`closet[0].count=1`);

  console.log("\n--- 5c. Drying done with nothing drying ----------------------------");
  await ev(`wearLog=[{itemId:"w",wornAt:${T - D}}]; lastWash=null; saveCloset()`); await drain();
  await open("dryBtn");
  check("it says nothing is drying", /Nothing is drying/.test($("washLoads").textContent) && $("washGo").disabled,
    $("washLoads").textContent);
  $("washCancel").onclick();

  console.log("\n--- 6. after the drying time, nothing is held ---------------------");
  await ev(`wearLog=[{itemId:"d",wornAt:${T - 3 * D},washedAt:${T - 30 * H}}]; saveCloset()`); await drain();
  check("a wash dry by the clock needs no tick", av("d") === 1);

  console.log(`\nlaundry_dry: ${passed} passed, ${failed} failed`);
  if (failed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
