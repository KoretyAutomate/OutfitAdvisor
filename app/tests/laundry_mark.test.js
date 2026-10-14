/**
 * laundry_mark.test.js — marking by hand what is still in the laundry (user,
 * 2026-10-14: "make it possible to select what's still in laundry ... when the user
 * starts using the app as well as marked laundry done wrongly, or when they missed
 * certain items to wash").
 *
 * Pinned:
 *   - the sheet starts from what is waiting now; ticking a clean garment holds it;
 *   - a garment marked by hand goes through "Laundry done" the same day;
 *   - it is not a day it was WORN: recent-wear history and "Worn today" ignore it;
 *   - ticking a drying garment takes the wash back; unticking frees a waiting one;
 *   - a stepper for garments owned more than once, capped at what is owned.
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
const H = 3600000, D = 24 * H;

const item = (id, label, colors, extra = {}) => ({id, label, category: "base", group: "tops",
  type: "t_shirt", roles: ["base"], colors, warmth: 1, formality: ["casual"], waterproof: false,
  count: 1, ...extra});

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const T = w.Date.now();
  w.Date.now = () => T;
  const $ = id => w.document.getElementById(id);
  const box = id => w.document.querySelector(`#dirtyList input[data-id="${id}"]`);
  const tick = (id, on) => { box(id).checked = on; box(id).onchange(); };
  const log = () => JSON.parse(ev("JSON.stringify(wearLog)"));
  const open = async () => { $("dirtyBtn").onclick(); await drain(); };
  const save = async () => { await $("dirtySave").onclick(); await drain(); };

  console.log("\n--- 1. first use: mark what is in the basket ----------------------");
  await ev(`closet=[${JSON.stringify(item("a", "white tee", ["white"]))},
    ${JSON.stringify(item("b", "navy tee", ["navy"]))},
    ${JSON.stringify(item("s", "black socks", ["black"], {count: 3}))}];
    wearLog=[]; lastWorn={}; saveCloset()`);
  await drain();
  check("the button shows once there is a closet", $("dirtyBtn").style.display === "");
  await open();
  check("the sheet opens", $("dirtyWrap").classList.contains("show"));
  check("nothing starts ticked on a clean closet", !box("a").checked && !box("b").checked);
  check("a garment owned once is a tick box, one owned more is a stepper",
    !!box("a") && !box("s") && !!w.document.querySelector('#dirtyList [data-id="s"] .stepper'));
  tick("a", true);
  const plus = w.document.querySelector('#dirtyList [data-id="s"] button[data-d="1"]');
  plus.onclick(); w.document.querySelector('#dirtyList [data-id="s"] button[data-d="1"]').onclick();
  check("the stepper counts", w.document.querySelector('#dirtyList [data-id="s"] b').textContent === "2");
  await save();
  check("the sheet closes", !$("dirtyWrap").classList.contains("show"));
  check("the ticked tee is out of rotation", ev(`avail(closet[0])`) === 0 && ev(`avail(closet[1])`) === 1);
  check("two of three socks are out", ev(`avail(closet[2])`) === 1);
  check("marked by hand", log().every(x => x.marked === true), log());
  check("…and not counted as worn", ev("JSON.stringify(lastWornAt())") === "{}", ev("JSON.stringify(lastWorn)"));

  console.log("\n--- 2. it can be washed the same day ------------------------------");
  $("laundryBtn").onclick(); await drain();
  const lb = l => w.document.querySelector(`#washLoads input[data-load="${l}"]`);
  check("its load is waiting", lb("white").checked && !lb("white").disabled);
  await $("washGo").onclick(); await drain();
  check("washed", log().filter(x => x.itemId === "a").every(x => x.washedAt === T), log());

  console.log("\n--- 3. a wash logged by mistake ----------------------------------");
  await open();
  check("a drying garment is not ticked", !box("a").checked);
  tick("a", true); await save();
  const a = log().filter(x => x.itemId === "a");
  check("ticking it takes the wash back — one wear, unwashed", a.length === 1 && a[0].washedAt == null, a);
  check("still out of rotation", ev(`avail(closet[0])`) === 0);

  console.log("\n--- 4. untick what is clean ---------------------------------------");
  await open();
  check("the sheet reads what is waiting", box("a").checked);
  tick("a", false); await save();
  check("back in rotation", ev(`avail(closet[0])`) === 1 && !log().some(x => x.itemId === "a"));

  console.log("\n--- 5. a real wear and a mark are different things ----------------");
  await ev(`wearLog=[{itemId:"b",wornAt:${T},marked:true}]; saveCloset()`);
  ev(`logWear("b")`);
  check("wearing it today still logs the wear", log().filter(x => x.itemId === "b" && !x.marked).length === 1, log());
  ev(`unlogWearToday("b")`);
  check("undoing the wear leaves the mark", log().filter(x => x.itemId === "b").length === 1
    && log()[0].marked === true, log());
  await ev(`wearLog=[{itemId:"b",wornAt:${T - D}}]; saveCloset()`);
  await open(); tick("b", false); await save();
  check("unticking a worn garment frees it but keeps the history",
    ev(`avail(closet[1])`) === 1 && ev(`"b" in lastWornAt()`), ev("JSON.stringify(lastWorn)"));

  console.log("\n--- 6. a drying garment past its passive timer -------------------");
  await ev(`wearLog=[{itemId:"a",wornAt:${T - 6 * D},washedAt:${T - H}}]; saveCloset()`);
  await open(); tick("a", true); await save();
  check("is held again, starting today", ev(`avail(closet[0])`) === 0
    && log()[0].wornAt === T && log()[0].marked === true, log());

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
