/**
 * laundry_status.test.js — "Laundry & drying status" (user, 2026-10-18: "rename washing
 * & drying done to washing & drying status? ... bundle undo last wash or undo last dry
 * in there, as well as what's still in laundry").
 *
 * Pinned:
 *   - the Closet tab's button says "Laundry & drying status" and opens one sheet;
 *   - that sheet says, per load, what waits to be washed and what is drying, until when;
 *   - it holds "Laundry done", "Drying done", "Laundry & drying done", the undo and
 *     "What's still in the laundry?", each of which hands over to its own sheet;
 *   - the undo says what it takes back: a wash, a dry, or a wash & dry.
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
  const shown = id => $(id).classList.contains("show");
  const status = () => $("laundryLoads").textContent.replace(/\s+/g, " ");
  const hub = async () => { $("laundryStatusBtn").onclick(); await drain(); };
  const lb = l => w.document.querySelector(`#washLoads input[data-load="${l}"]`);
  const BTN = {wash: "laundryBtn", dry: "dryBtn", both: "washDryBtn"};
  const wash = async ({mode = "wash", only} = {}) => {
    await hub(); $(BTN[mode]).onclick(); await drain();
    if (only) for (const l of ["white", "dark", "colorful"]) if (lb(l) && l !== only) { lb(l).checked = false; lb(l).onchange(); }
    await $("washGo").onclick(); await drain();
  };
  const reset = async wl => { await ev(`wearLog=${wl}; lastWash=null; saveCloset(); saveLastWash()`); await drain(); };

  await ev(`laundry.dryHours=24;
    closet=[${JSON.stringify(item("w", "white tee", ["white"]))},${JSON.stringify(item("d", "navy tee", ["navy"]))}];
    lastWorn={}`);
  await reset(`[{itemId:"w",wornAt:${T - 2 * D}},{itemId:"d",wornAt:${T - 2 * D}}]`);

  console.log("\n--- 1. one button on the Closet tab ------------------------------");
  check("it says Laundry & drying status", $("laundryStatusBtn").textContent === "Laundry & drying status",
    $("laundryStatusBtn").textContent);
  check("the three actions are no longer loose on the tab",
    ["laundryBtn", "dryBtn", "washDryBtn", "unwashBtn", "dirtyBtn"].every(id => !!$(id).closest("#laundryWrap")));
  await hub();
  check("it opens the status sheet", shown("laundryWrap"));

  console.log("\n--- 2. what each load holds --------------------------------------");
  check("each load says what waits to be washed", /Whites 1 to wash/.test(status()) && /Darks 1 to wash/.test(status()),
    status());
  check("no undo before any wash", $("unwashBtn").style.display === "none");
  check("'What's still in the laundry?' is here", $("dirtyBtn").style.display === "");
  $("laundryClose").onclick();
  check("Close closes it", !shown("laundryWrap"));

  console.log("\n--- 3. washed: drying, until when, and an undo that says wash -----");
  await wash({only: "white"});
  await hub();
  check("the whites are drying, with the time they are dry", /Whites 1 drying, dry by /.test(status()), status());
  check("the darks still wait", /Darks 1 to wash/.test(status()), status());
  check("the undo says wash", $("unwashBtn").textContent.startsWith("Undo last wash — Whites"), $("unwashBtn").textContent);

  console.log("\n--- 4. dried later: the undo says dry -----------------------------");
  T += 2 * H;
  await wash({mode: "dry", only: "white"});
  await hub();
  check("the whites are gone from the status", !/Whites/.test(status()), status());
  check("the undo says dry", $("unwashBtn").textContent.startsWith("Undo last dry — Whites"), $("unwashBtn").textContent);
  await $("unwashBtn").onclick(); await drain();
  check("undo, from the status sheet, puts them back to drying — and the sheet says so",
    shown("laundryWrap") && /Whites 1 drying/.test(status()), status());
  check("…and the undo is gone", $("unwashBtn").style.display === "none");

  console.log("\n--- 5. washed and dry in one go: the undo says wash & dry ---------");
  await reset(`[{itemId:"d",wornAt:${T - D}}]`);
  await wash({mode: "both"});
  await hub();
  check("nothing is waiting or drying", /Nothing is waiting to be washed or drying/.test(status()), status());
  check("the undo says wash & dry", $("unwashBtn").textContent.startsWith("Undo last wash & dry — Darks"),
    $("unwashBtn").textContent);
  await $("unwashBtn").onclick(); await drain();
  check("undo puts the darks back to be washed", /Darks 1 to wash/.test(status()), status());

  console.log("\n--- 6. a record from before 1.52 reads as a wash ------------------");
  await ev(`lastWash={at:${T},loads:["dark"],wears:[{itemId:"d",wornAt:${T - D}}]};
    wearLog=[{itemId:"d",wornAt:${T - D},washedAt:${T}}]; saveLastWash()`); await drain();
  check("no dry flag: Undo last wash", $("unwashBtn").textContent.startsWith("Undo last wash — "),
    $("unwashBtn").textContent);

  console.log("\n--- 7. each action hands over to its own sheet --------------------");
  for (const [id, head] of [["laundryBtn", "washed?"], ["dryBtn", "dry?"], ["washDryBtn", "washed and dry?"]]) {
    await hub(); $(id).onclick(); await drain();
    check(`${$(id).textContent} opens the wash sheet in its place, asking which loads are ${head}`,
      shown("washWrap") && !shown("laundryWrap") && $("washHead").textContent.endsWith(head), $("washHead").textContent);
    $("washCancel").onclick();
  }
  await hub(); $("dirtyBtn").onclick(); await drain();
  check("What's still in the laundry? opens its sheet in its place", shown("dirtyWrap") && !shown("laundryWrap"));
  $("dirtyCancel").onclick();

  console.log(`\nlaundry_status: ${passed} passed, ${failed} failed`);
  if (failed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
