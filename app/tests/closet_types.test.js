/**
 * closet_types.test.js — the second taxonomy level on the phone (user, 2026-08-20:
 * "Tops should be further split into inner, t-shirt, shirt, polo, etc.").
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * These functions are TWINS of server/vocab.py. If they drift, the server silently
 * drops a type the phone thought it had sent — types vanish on the way to the
 * advisor rather than raising anything. So section 1 checks the vocabulary itself
 * against the same rules server/tests/test_taxonomy.py checks the Python side
 * against, and every behavioural case below has a Python counterpart there.
 *
 * Run: npm test   (or: node tests/closet_types.test.js — jsdom is a devDependency since 2026-08-20)
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

console.log("\n--- 1. the vocabulary is internally consistent -------------------");
const GROUPS = ev("GROUPS"), TYPES = ev("TYPES"), TYPE_LABEL = ev("TYPE_LABEL");
const TYPE_ROLES = ev("TYPE_ROLES"), GROUP_CATS = ev("GROUP_CATS");
check("knitwear is no longer a group", !GROUPS.includes("knitwear"), GROUPS);
check("one-piece garments have a group of their own", GROUPS.includes("onepiece"), GROUPS);
check("the sweaters survived the dissolution as TYPES of Tops",
  ["sweater", "cardigan", "hoodie", "fleece", "waistcoat"].every(t => TYPES.tops.includes(t)),
  TYPES.tops);
check("the split the user asked for exists",
  ["t_shirt", "shirt", "polo"].every(t => TYPES.tops.includes(t)), TYPES.tops);
check("a dress is no longer filed as a pair of trousers",
  !TYPES.bottoms.includes("dress") && TYPES.onepiece.includes("dress"));
const allTypes = Object.values(TYPES).flat();
check("no type appears in two groups", new Set(allTypes).size === allTypes.length);
check("every type has human wording", allTypes.every(t => !!TYPE_LABEL[t]),
  allTypes.filter(t => !TYPE_LABEL[t]));
check("every type declares the roles it can play", allTypes.every(t => !!TYPE_ROLES[t]),
  allTypes.filter(t => !TYPE_ROLES[t]));
check("no type's roles are unreachable from its group",
  Object.entries(TYPES).every(([g, ts]) =>
    ts.every(t => TYPE_ROLES[t].some(r => GROUP_CATS[g].includes(r)))));
check("inner exists in exactly one group",
  Object.entries(GROUP_CATS).filter(([, c]) => c.includes("inner")).map(([g]) => g)
    .join() === "underwear");

console.log("\n--- 2. normType: a type is only meaningful inside its group -------");
const NT = [
  ["polo", "tops", "polo"],
  ["Polo", "tops", "polo"],
  ["dress-shoes", "footwear", "dress_shoes"],
  ["dress shoes", "footwear", "dress_shoes"],
  ["polo", "outerwear", null],       // right type, wrong group -> dropped
  ["nonsense", "tops", null],
  [null, "tops", null],
];
for (const [raw, grp, want] of NT) {
  const got = ev(`normType(${JSON.stringify(raw)}, ${JSON.stringify(grp)})`);
  check(`normType(${JSON.stringify(raw)}, "${grp}") -> ${JSON.stringify(want)}`, got === want, got);
}

console.log("\n--- 3. reconcileItem: twin parity with server/vocab.py ------------");
const R = (o) => ev(`reconcileItem(${JSON.stringify(o)})`);

let it = R({ id: "x", label: "l", category: "inner", group: "tops", roles: ["inner", "base"], type: "t_shirt" });
check("a visible top can never carry the inner role",
  it.group === "tops" && it.category !== "inner" && !it.roles.includes("inner"), it);

it = R({ id: "x", label: "l", category: "base", group: "tops", roles: ["inner", "mid", "outer"], type: "shirt" });
check("a demoted inner keeps the item's other roles",
  JSON.stringify(it.roles) === '["base","mid","outer"]', it);

it = R({ id: "x", label: "l", category: "base", group: "underwear", roles: ["base"], type: "undershirt" });
check("underwear stays closed",
  it.category === "inner" && JSON.stringify(it.roles) === '["inner"]', it);

it = R({ id: "x", label: "l", category: "outer", group: "outerwear", roles: ["mid", "outer"], type: "coat" });
check("a known type narrows the roles its group allows (a coat is outer)",
  JSON.stringify(it.roles) === '["outer"]', it);
it = R({ id: "x", label: "l", category: "outer", group: "outerwear", roles: ["mid", "outer"] });
check("without a type the group's full set stands",
  JSON.stringify(it.roles) === '["mid","outer"]', it);
it = R({ id: "x", label: "l", category: "outer", group: "outerwear", roles: ["mid", "outer"], type: "blazer" });
check("a blazer keeps both layers it can play",
  JSON.stringify(it.roles) === '["mid","outer"]', it);

it = R({ id: "x", label: "l", category: "base", group: "onepiece", roles: ["base", "bottoms"], type: "dress" });
check("a one-piece garment is confined to the base slot",
  JSON.stringify(it.roles) === '["base"]' && it.category === "base", it);

it = R({ id: "x", label: "l", category: "nonsense", group: "nonsense", roles: ["nonsense"], type: "nonsense" });
check("reconcile is total — junk in, a legal item out",
  GROUPS.includes(it.group) && it.roles.length > 0 && it.type === null, it);

it = R({ id: "x", label: "l", category: "base", type: "puffer" });
check("the type names the group when the group is missing",
  it.group === "outerwear" && it.type === "puffer", it);

check("no type is ever invented for an untyped item",
  R({ id: "x", label: "l", category: "base", group: "tops" }).type === null);

console.log("\n--- 4. migration: nobody's closet starts over ---------------------");
it = R({ id: "x", label: "l", category: "mid", group: "knitwear", roles: ["mid", "outer"], type: "sweater" });
check("a knitwear item becomes a Top and keeps its type",
  it.group === "tops" && it.type === "sweater", it);
check("a knitwear item keeps the layers it could play",
  JSON.stringify(it.roles) === '["mid","outer"]', it);
it = R({ id: "x", label: "l", category: "bottoms", group: "bottoms", roles: ["bottoms"], type: "dress" });
check("a dress saved under bottoms moves to onepiece",
  it.group === "onepiece" && it.type === "dress", it);
// Without this entry the type is DROPPED (socks is no longer a type of underwear),
// the item stays in underwear with type=null, and the server's NON_SLOT filter —
// which keys on the type — lets it through as a legal undershirt.
it = R({ id: "x", label: "l", category: "inner", group: "underwear", roles: ["inner"], type: "socks" });
check("socks saved under underwear move to footwear and keep their type",
  it.group === "footwear" && it.type === "socks", it);
check("...and stop being a candidate for the undershirt slot",
  JSON.stringify(it.roles) === '["footwear"]', it);
const LTG = ev("LEGACY_TYPE_GROUP"), TYPES_ = ev("TYPES");
check("every legacy regroup lands on a group that owns that type",
  Object.entries(LTG).every(([k, dest]) => TYPES_[dest].includes(k.split("|")[1])), LTG);
check("migrateItem is reconcileItem — one repair pass on load",
  ev(`migrateItem({id:"x",label:"l",category:"inner",group:"tops"}).category`) !== "inner");

(async () => {
  for (let i = 0; i < 20 && !ev("state.baseUrl"); i++) await drain();
  await new Promise(r => setTimeout(r, 30));   // let load()'s last await settle

  console.log("\n--- 5. the folder shows the second level --------------------------");
  ev(`closet=[
    {id:"i1",label:"white tee",category:"base",group:"tops",type:"t_shirt",roles:["base"],count:1,colors:[],warmth:1,formality:["casual"],waterproof:false},
    {id:"i2",label:"navy pique",category:"base",group:"tops",type:"polo",roles:["base"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
    {id:"i3",label:"oxford",category:"base",group:"tops",type:"shirt",roles:["base","mid","outer"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
    {id:"i4",label:"grey crewneck",category:"mid",group:"tops",type:"sweater",roles:["mid"],count:1,colors:[],warmth:4,formality:["casual"],waterproof:false}
  ]; wearLog=[]; closetFolded=new Set(); trips=[];`);
  await ev("renderCloset()"); await drain();
  const heads = [...w.document.querySelectorAll(".folderHead b")].map(e => e.textContent);
  check("all four still live in ONE folder", JSON.stringify(heads) === '["Tops"]', heads);
  const subs = [...w.document.querySelectorAll(".subHead .st")].map(e => e.textContent);
  check("the folder is split by type, in vocabulary order",
    JSON.stringify(subs) === '["T-shirt","Shirt","Polo shirt","Sweater / pullover"]', subs);
  const subCounts = [...w.document.querySelectorAll(".subHead .sc")].map(e => e.textContent);
  check("each sub-section counts its own items",
    JSON.stringify(subCounts) === '["1","1","1","1"]', subCounts);
  check("every item still renders as a tile", w.document.querySelectorAll(".item").length === 4);

  // GROUP_ALIAS is defence-in-depth everywhere else — reconcileItem reaches "tops"
  // for a knitwear item via GROUP_FROM_TYPE or GROUP_FROM_CAT anyway, so deleting
  // the table breaks no other assertion here. THIS is the path where it is the only
  // thing doing the work: rendering an item that has not been through migrateItem.
  ev(`closet=[
    {id:"k1",label:"grey crewneck",category:"mid",group:"knitwear",type:"sweater",roles:["mid"],count:1,colors:[],warmth:4,formality:["casual"],waterproof:false}
  ]; wearLog=[]; closetFolded=new Set();`);
  await ev("renderCloset()"); await drain();
  const kHeads = [...w.document.querySelectorAll(".folderHead b")].map(e => e.textContent);
  check("an UNMIGRATED knitwear item still renders under Tops",
    JSON.stringify(kHeads) === '["Tops"]', kHeads);
  check("...and there is no Knitwear folder left to render it into",
    !kHeads.includes("Knitwear"), kHeads);

  console.log("\n--- 6. an untyped closet looks exactly like it did yesterday ------");
  ev(`closet=[
    {id:"u1",label:"a top",category:"base",group:"tops",roles:["base"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false},
    {id:"u2",label:"another top",category:"base",group:"tops",roles:["base"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false}
  ]; wearLog=[]; closetFolded=new Set();`);
  await ev("renderCloset()"); await drain();
  check("a sole untyped section gets no 'Other' heading",
    w.document.querySelectorAll(".subHead").length === 0,
    [...w.document.querySelectorAll(".subHead .st")].map(e => e.textContent));
  check("and its tiles still render", w.document.querySelectorAll(".item").length === 2);

  console.log("\n--- 7. a MIXED folder does label the untyped remainder ------------");
  ev(`closet=[
    {id:"m1",label:"navy pique",category:"base",group:"tops",type:"polo",roles:["base"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
    {id:"m2",label:"a top",category:"base",group:"tops",roles:["base"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false}
  ]; wearLog=[]; closetFolded=new Set();`);
  await ev("renderCloset()"); await drain();
  const mixed = [...w.document.querySelectorAll(".subHead .st")].map(e => e.textContent);
  check("Other comes LAST, after every named type",
    JSON.stringify(mixed) === '["Polo shirt","Other"]', mixed);

  console.log("\n--- 8. the edit sheet: Kind follows the folder --------------------");
  await ev(`openSheet(closet[0],{isNew:false})`); await drain();
  const opts = () => [...w.document.querySelectorAll("#shType option")].map(o => o.value);
  check("the Kind picker offers this group's types", opts().includes("polo") && opts().includes("t_shirt"), opts());
  check("...and no other group's", !opts().includes("coat"), opts());
  check("'not specified' stays offered — an untyped item is legitimate", opts()[0] === "");
  check("the item's current Kind is selected", w.document.getElementById("shType").value === "polo");

  w.document.getElementById("shGroup").value = "outerwear";
  w.document.getElementById("shGroup").onchange();
  await drain();
  check("moving the folder rebuilds the Kind picker",
    opts().includes("coat") && !opts().includes("polo"), opts());
  check("a Kind that cannot survive the move is dropped, not reinterpreted",
    w.document.getElementById("shType").value === "" && ev("sheet.item.type") === null);
  check("and the layer follows the folder",
    ev(`GROUP_CATS["outerwear"].includes(sheet.item.category)`), ev("sheet.item.category"));

  w.document.getElementById("shType").value = "coat";
  w.document.getElementById("shType").onchange();
  await drain();
  const chips = [...w.document.querySelectorAll("#shRoles button")].map(b => b.dataset.role);
  check("choosing Coat narrows the role chips to what a coat can be",
    JSON.stringify(chips) === '["outer"]', chips);

  console.log("\n--- 9. the role chips never offer the contradiction ---------------");
  await ev(`openSheet({id:"z",label:"tee",category:"base",group:"tops",type:"t_shirt",
    roles:["base"],count:1,colors:[],warmth:1,formality:["casual"],waterproof:false},{isNew:false})`);
  await drain();
  const topChips = [...w.document.querySelectorAll("#shRoles button")].map(b => b.dataset.role);
  check("a Top is never offered the Inner chip", !topChips.includes("inner"), topChips);
  await ev(`openSheet({id:"z",label:"vest",category:"inner",group:"underwear",type:"undershirt",
    roles:["inner"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false},{isNew:false})`);
  await drain();
  const underChips = [...w.document.querySelectorAll("#shRoles button")].map(b => b.dataset.role);
  check("underwear is offered Inner and nothing else",
    JSON.stringify(underChips) === '["inner"]', underChips);

  console.log("\n--- 10. the server is told the type -------------------------------");
  ev(`closet=[
    {id:"p1",label:"navy pique",category:"base",group:"tops",type:"polo",roles:["base"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
    {id:"p2",label:"a top",category:"base",group:"tops",roles:["base"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false}
  ]; wearLog=[]; trips=[];`);
  const payload = ev("closetPayload()");
  check("the outfit payload carries the type", payload.find(p => p.id === "p1").type === "polo", payload);
  check("an untyped item goes out as null, not as a guess",
    payload.find(p => p.id === "p2").type === null, payload);
  const pack = ev(`packPayload({start:"2026-09-01",end:"2026-09-04",laundryBefore:false})`);
  check("the packing payload carries the type too — a business trip needs the shirt",
    pack.find(p => p.id === "p1").type === "polo", pack);
  check("the packing payload carries the group", pack.find(p => p.id === "p1").group === "tops", pack);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
