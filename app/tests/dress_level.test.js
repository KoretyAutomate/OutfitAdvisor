/**
 * dress_level.test.js — one Dress level in place of the Works-for tags, and only
 * the fields that apply (user, 2026-10-22: "anything that we don't need, let's
 * remove it so that users don't get confused. We likely need to keep that
 * information in the backend though").
 *
 * Pinned:
 *   - the sheet has no Works-for, Category or Clothing group control;
 *   - the level buttons set and clear `level`; Save writes it with the old tags kept
 *     in step (`formality`), and a cleared level goes back to the guess;
 *   - an untouched level defers to what the photo scan wrote meanwhile;
 *   - the scan's level brings the tags with it;
 *   - sleeves, pattern, dress level, waterproof and the layer chips show only where
 *     they say something about the garment.
 *
 * Loads the REAL app/www/index.html in jsdom.
 * Run: npm test   (or: node tests/dress_level.test.js)
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

const item = (id, label, extra = {}) => ({id, label, category: "bottoms", group: "bottoms", type: "trousers",
  roles: ["bottoms"], colors: ["beige"], warmth: 1, formality: ["smart"], waterproof: false, count: 1,
  photo: false, ...extra});

(async () => {
  const w = page();
  await w.eval("appReady");
  const $ = id => w.document.getElementById(id);
  const shown = id => $(id).style.display !== "none";
  const saved = () => JSON.parse(w.eval("JSON.stringify(closet)"));
  const lit = () => [...$("shLevel").children].filter(b => b.classList.contains("on")).map(b => +b.dataset.l);

  console.log("\n--- 1. what the sheet no longer asks --------------------------------");
  check("no Works-for, Category or Clothing group control",
    !$("shForm") && !$("shCat") && !$("shGroup"));

  console.log("\n--- 2. the level ----------------------------------------------------");
  await w.eval(`closet=[${JSON.stringify(item("c1", "beige cargo pants"))}]; saveCloset()`);
  await w.eval(`openSheet(closet[0],{isNew:false})`); await drain();
  check("an unset level lights nothing and says it is guessed",
    lit().length === 0 && /guessed/.test($("shLevelHint").textContent), [lit(), $("shLevelHint").textContent]);
  $("shLevel").querySelector('[data-l="3"]').click(); await drain();
  check("tapping Smart casual lights it", JSON.stringify(lit()) === "[3]", lit());
  await $("shSave").onclick(); await drain();
  let s = saved()[0];
  check("Save writes the level", s.level === 3, s);
  check("…and keeps the old tags in step for packing and the rollback engine",
    JSON.stringify(s.formality) === '["casual","smart"]', s.formality);

  await w.eval(`openSheet(closet[0],{isNew:false})`); await drain();
  $("shLevel").querySelector('[data-l="1"]').click(); await drain();
  await $("shSave").onclick(); await drain();
  s = saved()[0];
  check("Sport is the old Active", s.level === 1 && JSON.stringify(s.formality) === '["active"]', s);

  await w.eval(`openSheet(closet[0],{isNew:false})`); await drain();
  $("shLevel").querySelector('[data-l="1"]').click(); await drain();
  check("tapping the lit one clears it", lit().length === 0, lit());
  await $("shSave").onclick(); await drain();
  s = saved()[0];
  check("a cleared level is gone — the guess again, and the photo read may fill it", !("level" in s), s);

  console.log("\n--- 3. an untouched level defers to the scan ------------------------");
  await w.eval(`openSheet(closet[0],{isNew:false})`); await drain();
  await w.eval(`closet[0].level=4`);
  $("shLabel").value = "beige cargo trousers";
  await $("shSave").onclick(); await drain();
  s = saved()[0];
  check("a level the scan wrote while the sheet was open survives Save", s.level === 4 && s.label === "beige cargo trousers", s);
  await w.eval(`openSheet(closet[0],{isNew:false})`); await drain();
  await w.eval(`closet[0].level=2`);
  $("shLevel").querySelector('[data-l="3"]').click(); await drain();
  await $("shSave").onclick(); await drain();
  check("…but one the wearer picked wins over it", saved()[0].level === 3, saved()[0]);

  console.log("\n--- 4. the scan brings the tags with its level ----------------------");
  await w.eval(`closet=[${JSON.stringify(item("c2", "black cargo pants", {photo: true, brand: "", sleeve: null,
    pattern: null, fabric: null, formality: ["casual", "smart"]}))}]; saveCloset()`);
  w.localStorage.setItem("oa.photo.c2", "P".repeat(200));
  w.fetch = async () => ({ok: true, status: 200, json: async () => ({brand: null, level: 2})});
  await w.eval("scanBrands()"); await drain();
  s = saved()[0];
  check("the scan's level 2 makes it Casual", s.level === 2 && JSON.stringify(s.formality) === '["casual"]', s);

  console.log("\n--- 5. only the fields that apply ------------------------------------");
  const open = async extra => {
    await w.eval(`closeSheet(); openSheet(${JSON.stringify(item("v", "thing", extra))},{isNew:true})`);
    await drain();
  };
  await open({});
  check("trousers: no sleeves, no layer chips", !shown("shSleeveBox") && !shown("shRolesBox"));
  check("trousers: pattern, level and waterproof", shown("shPatternBox") && shown("shLevelBox") && shown("shWpBox"));
  await open({group: "tops", type: "shirt", category: "base", roles: ["base", "mid", "outer"]});
  check("a shirt: sleeves, pattern, level and the layer chips",
    shown("shSleeveBox") && shown("shPatternBox") && shown("shLevelBox") && shown("shRolesBox"));
  await open({group: "underwear", type: "undershirt", category: "inner", roles: ["inner"]});
  check("an undershirt: sleeves only — no pattern, level or waterproof",
    shown("shSleeveBox") && !shown("shPatternBox") && !shown("shLevelBox") && !shown("shWpBox"));
  await open({group: "accessories", type: "belt", category: "accessories", roles: ["accessories"]});
  check("a belt: no sleeves, pattern or level", !shown("shSleeveBox") && !shown("shPatternBox") && !shown("shLevelBox"));
  $("shType").value = "coat"; $("shType").onchange(); await drain();
  check("changed to a coat on the sheet, the level shows", shown("shLevelBox") && w.eval("sheet.item.group") === "outerwear");
  w.eval("closeSheet()");

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
