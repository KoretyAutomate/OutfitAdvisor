/**
 * closet_types.test.js — the second taxonomy level: group > type
 * (user, 2026-08-14).
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * Two things are under test, both of which fail QUIETLY:
 *   - normType() is a TWIN of normalize_type() in server/vocab.py. The parity
 *     table below is duplicated verbatim in server/tests/test_taxonomy.py. If they
 *     drift, the phone offers a type the server silently drops, and nobody sees an
 *     error — the advice just stops knowing a polo from a tee.
 *   - the closet grid must nest types INSIDE group folders without disturbing the
 *     folders themselves, and a closet saved before types existed must still look
 *     exactly like it did yesterday rather than growing an "Other" header on
 *     every tile.
 *
 * Run: NODE_PATH=<...>/node_modules node tests/closet_types.test.js
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
const ev = (c) => w.eval(c);
const drain = () => new Promise(r => setTimeout(r, 0));

// (input, group, expected) — MIRRORED in server/tests/test_taxonomy.py::PARITY
const PARITY = [
  ["polo", "tops", "polo"],
  ["Polo", "tops", "polo"],
  ["t-shirt", "tops", "t_shirt"],
  ["dress shoes", "footwear", "dress_shoes"],
  ["polo", "outerwear", null],
  ["kimono", "tops", null],
  ["", "tops", null],
  [null, "tops", null],
  ["polo", null, null],
];

(async () => {
  for (let i = 0; i < 20 && !ev("state.baseUrl"); i++) await drain();
  await new Promise(r => setTimeout(r, 30));   // let load()'s last await settle

  console.log("\n--- 1. normType: twin parity with server/vocab.py ----------------");
  for (const [v, g, want] of PARITY) {
    const got = ev(`normType(${JSON.stringify(v)}, ${JSON.stringify(g)})`);
    check(`normType(${JSON.stringify(v)}, ${JSON.stringify(g)}) -> ${JSON.stringify(want)}`,
      got === want, got);
  }
  check("every group offers at least one type",
    ev(`GROUPS.every(g=>(TYPES[g]||[]).length>0)`));
  check("every type has a human label",
    ev(`Object.values(TYPES).flat().every(t=>!!TYPE_LABEL[t])`));

  console.log("\n--- 2. an old item is not given a type it never had ---------------");
  // A wrong type would go into the advisor's prompt as fact. None is honest.
  check("migrateItem leaves a pre-2026-08-14 item untyped",
    ev(`migrateItem({id:"x",label:"l",category:"base"}).type`) === null);
  check("a type that does not fit the item's group is dropped on load",
    ev(`migrateItem({id:"x",label:"l",category:"outer",group:"outerwear",type:"polo"}).type`) === null);
  check("a type that fits survives",
    ev(`migrateItem({id:"x",label:"l",category:"base",group:"tops",type:"polo"}).type`) === "polo");

  console.log("\n--- 3. the grid nests types inside the group folders --------------");
  const seed = () => ev(`closet=[
    {id:"i1",label:"white tee",category:"base",group:"tops",type:"t_shirt",roles:["base"],count:2,colors:[],warmth:2,formality:["casual"],waterproof:false},
    {id:"i2",label:"navy polo",category:"base",group:"tops",type:"polo",roles:["base"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
    {id:"i3",label:"oxford shirt",category:"base",group:"tops",type:"shirt",roles:["base","outer"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
    {id:"i4",label:"mystery top",category:"base",group:"tops",roles:["base"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false},
    {id:"i5",label:"wool coat",category:"outer",group:"outerwear",type:"coat",roles:["outer"],count:1,colors:[],warmth:5,formality:["smart"],waterproof:false}
  ]; wearLog=[]; closetFolded=new Set();`);
  seed();
  await ev("renderCloset()"); await drain();

  const heads = [...w.document.querySelectorAll(".folderHead b")].map(e => e.textContent);
  check("the group folders are untouched by the new level",
    JSON.stringify(heads) === '["Tops","Outerwear"]', heads);
  const subs = [...w.document.querySelectorAll(".folder")]
    .map(f => [...f.querySelectorAll(".subHead .st")].map(e => e.textContent));
  check("Tops is subdivided in vocabulary order, with Other LAST",
    JSON.stringify(subs[0]) === '["T-shirt","Shirt","Polo shirt","Other"]', subs[0]);
  check("a folder with one typed item still labels it",
    JSON.stringify(subs[1]) === '["Coat"]', subs[1]);
  check("every item is still exactly one tile",
    w.document.querySelectorAll(".item").length === 5,
    w.document.querySelectorAll(".item").length);

  console.log("\n--- 4. a closet with no types looks like it did yesterday ---------");
  ev(`closet=[
    {id:"o1",label:"a top",category:"base",group:"tops",roles:["base"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false},
    {id:"o2",label:"another top",category:"base",group:"tops",roles:["base"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false}
  ]; wearLog=[];`);
  await ev("renderCloset()"); await drain();
  check("no 'Other' heading when Other is all there is",
    w.document.querySelectorAll(".subHead").length === 0,
    [...w.document.querySelectorAll(".subHead .st")].map(e => e.textContent));
  check("the tiles are still there", w.document.querySelectorAll(".item").length === 2);

  console.log("\n--- 5. the server is told the type --------------------------------");
  ev("trips=[];");
  seed();
  const payload = ev("closetPayload()");
  check("payload carries the type", payload.find(p => p.id === "i2").type === "polo");
  check("an untyped item sends null, not a guess",
    payload.find(p => p.id === "i4").type === null, payload.find(p => p.id === "i4"));

  // Regression, 2026-08-14 (found by the pre-push reviewer): the type reached the
  // daily advice but not the packing list, so "pack a shirt" for a business trip
  // could not tell a polo from a tee — the one decision the type exists to make.
  const pack = ev(`packPayload({start:"2030-01-10",end:"2030-01-14",laundryBefore:false})`);
  const packed = pack.find(p => p.id === "i2");
  check("the packing payload carries the type too", packed && packed.type === "polo", packed);
  check("and the group and roles that qualify it",
    packed && packed.group === "tops" && Array.isArray(packed.roles), packed);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
