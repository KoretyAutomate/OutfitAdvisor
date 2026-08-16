/**
 * closet_groups.test.js — folders + seasonal roles (user request 2026-08-10).
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * Two things are under test, and both are the kind that fail quietly:
 *   - normRoles() is a TWIN of normalize_roles() in server/llm.py. If they drift,
 *     the phone and the server disagree about what an item may be worn as, and the
 *     server silently clears picks the app thought were fine. The parity table
 *     below is duplicated verbatim in server/tests/check_closet_dedupe.py.
 *   - migrateItem() has to fill group/roles for closets saved BEFORE these fields
 *     existed. Without it every pre-existing photo lands in the wrong folder, or
 *     none at all.
 *
 * Run: NODE_PATH=<...>/node_modules node tests/closet_groups.test.js
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

const dom = new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
});
const w = dom.window;
const ev = (code) => w.eval(code);
const drain = () => new Promise(r => setTimeout(r, 0));

console.log("\n--- 1. normRoles: twin parity with server/llm.py -----------------");
const CASES = [
  [[], "base", ["base"]],                                  // old closet keeps working
  [["inner", "base", "outer"], "inner", ["inner"]],         // inner is closed
  [["base", "outer"], "base", ["base", "outer"]],           // seasonal shirt
  [["outer", "base", "mid"], "base", ["base", "mid", "outer"]], // stable order
  [["base", "hat", ""], "base", ["base"]],                  // junk dropped
  [["mid"], "outer", ["mid"]],                              // explicit beats category
];
for (const [roles, cat, want] of CASES) {
  const got = ev(`normRoles(${JSON.stringify(roles)}, ${JSON.stringify(cat)})`);
  check(`normRoles(${JSON.stringify(roles)}, "${cat}") -> ${JSON.stringify(want)}`,
    JSON.stringify(got) === JSON.stringify(want), got);
}
check("a visible garment can never claim inner",
  !ev(`normRoles(["base","outer"],"base")`).includes("inner"));

console.log("\n--- 2. migrateItem backfills closets saved before these fields ----");
const MIG = [["inner", "underwear"], ["base", "tops"], ["mid", "knitwear"],
             ["outer", "outerwear"], ["bottoms", "bottoms"], ["footwear", "footwear"],
             ["accessories", "accessories"]];
for (const [cat, grp] of MIG) {
  const it = ev(`migrateItem({id:"x",label:"l",category:"${cat}"})`);
  check(`a legacy "${cat}" item files under ${grp}`, it.group === grp, it);
}
check("legacy roles default to the item's own category",
  JSON.stringify(ev(`migrateItem({id:"x",label:"l",category:"outer"}).roles`)) === '["outer"]');
check("migrate does not clobber a group already set",
  ev(`migrateItem({id:"x",label:"l",category:"base",group:"outerwear"}).group`) === "outerwear");

console.log("\n--- 3. the grid renders folders, not a flat list ------------------");
// The page's init IIFE calls load(), which is async and reassigns `closet` from
// storage. Seeding before that settles gets silently overwritten — wait it out.
const seed = () => ev(`closet=[
  {id:"i1",label:"undershirt",category:"inner",group:"underwear",roles:["inner"],count:2,colors:[],warmth:2,formality:["casual"],waterproof:false},
  {id:"i2",label:"oxford shirt",category:"base",group:"tops",roles:["base","mid","outer"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
  {id:"i3",label:"white tee",category:"base",group:"tops",roles:["base"],count:3,colors:[],warmth:2,formality:["casual"],waterproof:false},
  {id:"i4",label:"wool coat",category:"outer",group:"outerwear",roles:["outer"],count:1,colors:[],warmth:5,formality:["smart"],waterproof:false}
]; wearLog=[]; closetFolded=new Set();`);
(async () => {
  for (let i = 0; i < 20 && !ev("state.baseUrl"); i++) await drain();
  await new Promise(r => setTimeout(r, 30));   // let load()'s last await settle
  seed();
  await ev("renderCloset()"); await drain();
  const heads = [...w.document.querySelectorAll(".folderHead b")].map(e => e.textContent);
  check("one folder per non-empty group, in vocabulary order",
    JSON.stringify(heads) === '["Underwear","Tops","Outerwear"]', heads);
  check("empty groups are not shown at all",
    !heads.includes("Bottoms") && !heads.includes("Footwear"), heads);
  const counts = [...w.document.querySelectorAll(".fcount")].map(e => e.textContent);
  check("each folder counts wearable/total items", JSON.stringify(counts) === '["2/1","4/2","1/1"]', counts);
  check("every item still renders as a tile",
    w.document.querySelectorAll(".item").length === 4);

  console.log("\n--- 4. folders collapse, and the state survives a relaunch -------");
  w.document.querySelector('.folderHead[data-grp="tops"]').click();
  await drain(); await drain();
  check("clicking a folder head collapses it", ev(`closetFolded.has("tops")`));
  // Tops holds TWO items (oxford + tee), so collapsing it leaves 4 - 2 = 2.
  check("a collapsed folder renders none of its tiles",
    w.document.querySelectorAll(".item").length === 2,
    w.document.querySelectorAll(".item").length);
  check("the collapsed set is persisted",
    (w.localStorage.getItem("oa.closetFolded") || "").includes("tops"),
    w.localStorage.getItem("oa.closetFolded"));

  console.log("\n--- 5. the server is told the group and the roles -----------------");
  ev("trips=[];");
  const payload = ev("closetPayload()");
  const shirt = payload.find(p => p.id === "i2");
  check("payload carries roles so the model can pick a seasonal role",
    JSON.stringify(shirt.roles) === '["base","mid","outer"]', shirt);
  check("payload carries the clothing group", shirt.group === "tops", shirt);
  const under = payload.find(p => p.id === "i1");
  check("underwear goes out with inner only", JSON.stringify(under.roles) === '["inner"]', under);


  console.log("\n--- 6. the outfit shows YOUR garment, not just its name ----------");
  // A name ("navy merino crew-neck") is not how anyone recognises their own
  // clothes; the photo is (user, 2026-08-16). Slots filled by a generic
  // suggestion must keep the category icon, so "mine" vs "suggested" stays
  // visible at a glance.
  ev(`photoLoad = async (id) => (id === "i2" ? "data:image/jpeg;base64,AAAA" : null);`);
  ev(`renderOutfit({inner:"Light cotton undershirt",base:"oxford shirt",mid:"None needed",
        outer:"None needed",bottoms:"dark chinos",footwear:"Sneakers",accessories:"None",
        tip:"t"}, "text", "llm",
        {closetUsed:true, picks:{base:"i2", bottoms:"i3"}, closetSent:true});`);
  await drain(); await drain(); await drain();
  const baseIc = w.document.querySelector('#outfitList li[data-slot="base"] .ic');
  const innerIc = w.document.querySelector('#outfitList li[data-slot="inner"] .ic');
  check("a slot filled from the closet shows its photo",
    !!baseIc && !!baseIc.querySelector("img.thumb"), baseIc && baseIc.innerHTML);
  check("a generic slot keeps the category icon",
    !!innerIc && !innerIc.querySelector("img") && innerIc.textContent.trim().length > 0,
    innerIc && innerIc.innerHTML);
  check("a picked item with no photo on disk falls back to the icon",
    (() => { const e = w.document.querySelector('#outfitList li[data-slot="bottoms"] .ic');
             return !!e && !e.querySelector("img"); })());

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
