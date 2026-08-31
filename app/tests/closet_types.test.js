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
/* A second, untouched page. The photo-store assertions replace photoLoad/photoSave
   to force failures, so the read-back check below needs a copy nobody has stubbed. */
const page2 = () => new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
}).window;
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
  // Wait for the page to finish initialising. appReady is the real signal;
  // polling for a field load() happens to set early is a guess about one.
  await ev("appReady");

  console.log("\n--- 5. the folder shows the second level --------------------------");
  ev(`closet=[
    {id:"i1",label:"white tee",category:"base",group:"tops",type:"t_shirt",roles:["base"],count:1,colors:[],warmth:1,formality:["casual"],waterproof:false},
    {id:"i2",label:"navy pique",category:"base",group:"tops",type:"polo",roles:["base"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
    {id:"i3",label:"oxford",category:"base",group:"tops",type:"shirt",roles:["base","mid","outer"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false},
    {id:"i4",label:"grey crewneck",category:"mid",group:"tops",type:"sweater",roles:["mid"],count:1,colors:[],warmth:4,formality:["casual"],waterproof:false}
  ]; wearLog=[]; closetFolded=new Set(); trips=[];`);
  await ev("renderCloset()"); await drain();
  const heads = [...w.document.querySelectorAll(".folderHead b")].map(e => e.textContent);
  /* Folders are the recommendation's SLOTS as of 2026-08-23, so the three base
     garments and the one mid garment separate — which is the point: the closet
     now reads the way the advice does. */
  check("they file by the slot the advice fills them into",
    JSON.stringify(heads) === '["Base layer","Mid layer"]', heads);
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
  /* Since folders became slots this renders by `category`, so GROUP_ALIAS is no
     longer what places the tile — but the item must still SURVIVE, and its type
     must still resolve through the retired group name. */
  check("an UNMIGRATED knitwear item still renders, under its slot",
    JSON.stringify(kHeads) === '["Mid layer"]', kHeads);
  check("...and there is no Knitwear folder left to render it into",
    !kHeads.includes("Knitwear"), kHeads);
  check("its type still resolves through the retired group name",
    [...w.document.querySelectorAll(".subHead .st")].map(e => e.textContent)[0] === "Sweater / pullover",
    [...w.document.querySelectorAll(".subHead .st")].map(e => e.textContent));

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

  console.log("\n--- 9. reading the type out of the label (2026-08-23) ----------");
  // Every closet saved before 2026-08-14 has no type, so all of it filed under the
  // unlabelled "Other" block — one flat lump inside Tops and Bottoms, which is what
  // the user reported as "the classification got narrower".
  const NOUNS = [
    ["Grey v-neck t-shirt", "tops", "t_shirt"],   // must beat the "shirt" substring
    ["White oxford shirt",  "tops", "shirt"],
    ["Navy polo",           "tops", "polo"],
    ["Grey hoodie",         "tops", "hoodie"],
    ["Blue jeans",       "bottoms", "jeans"],
    ["Black chinos",     "bottoms", "trousers"],
    ["Black tights",     "bottoms", "leggings"],
    ["Down jacket",    "outerwear", "puffer"],    // must beat the "jacket" substring
    ["Navy blazer",    "outerwear", "blazer"],
    ["Sports bra",     "underwear", "bra"],
    ["Running shoes",   "footwear", "sneakers"],
    ["Wool socks",      "footwear", "socks"],
    ["Brown leather belt", "accessories", "belt"],
  ];
  for (const [label, grp, want] of NOUNS)
    check(`"${label}" in ${grp} reads as ${want}`,
      ev(`typeFromLabel(${JSON.stringify(label)},${JSON.stringify(grp)})`) === want,
      ev(`typeFromLabel(${JSON.stringify(label)},${JSON.stringify(grp)})`));

  // The group restricts the vocabulary: "denim" alone means jeans, but a denim
  // JACKET is outerwear, and jeans are not a legal type there.
  check("a denim jacket is a jacket, not jeans",
    ev(`typeFromLabel("Denim jacket","outerwear")`) === "jacket",
    ev(`typeFromLabel("Denim jacket","outerwear")`));

  // Precision over recall: silence is a correct answer, and the item keeps filing
  // under Other exactly as it does today.
  check("a label naming no garment stays untyped",
    ev(`typeFromLabel("Something vague","tops")`) === null);
  check("an empty label stays untyped", ev(`typeFromLabel("","tops")`) === null);
  check("a label of only punctuation stays untyped", ev(`typeFromLabel("---","tops")`) === null);

  console.log("\n--- 10. inference only ever FILLS a gap, and only on load ------");
  // migrateItem is the load path; that is the ONLY place a label is read.
  const filled = ev(`migrateItem({id:"x1",label:"Navy polo",category:"base",group:"tops",count:1})`);
  check("an untyped item gets the type its label names", filled.type === "polo", filled);
  check("and is marked as filed by name, not by the classifier",
    filled.typeFrom === "label", filled);
  const stated = ev(`migrateItem({id:"x2",label:"Navy polo",category:"base",group:"tops",type:"shirt",count:1})`);
  check("a type the classifier gave is NEVER overwritten by the label",
    stated.type === "shirt", stated);
  check("and carries no by-name marker", !stated.typeFrom, stated);

  /* The Kind selector offers "— not specified —", and an untyped item is a
     perfectly good wardrobe entry. Inferring on every reconcile made that option
     inert: the user picked it, the label still said "Navy polo", and polo came
     straight back. Raised by the pre-push reviewer, 2026-08-23. */
  // Driven through the real picker: "not specified" is a DECISION, and it is the
  // only place the marker is set. Inferring it from "reconcile ran and there was no
  // Kind" marks items nobody decided about — a photo added while /classify was
  // unreachable, for one — and the re-scan then refuses the very items it is for.
  ev(`sheet={item:{id:"x3",label:"Navy polo",category:"base",group:"tops",type:"polo",
                   roles:["base"],count:1,colors:[],warmth:2,formality:["casual"],waterproof:false},isNew:false};
      paintTypes();
      w0=document.getElementById("shType"); w0.value=""; w0.onchange();`);
  const cleared = ev(`sheet.item`);
  check("choosing '— not specified —' actually clears the Kind", cleared.type === null, cleared);
  check("and the choice is remembered", cleared.typeCleared === true, cleared);
  const afterLoad = ev(`migrateItem(${JSON.stringify(cleared)})`);
  check("and survives the next load — the backfill does not undo it",
    afterLoad.type === null, afterLoad);

  // Choosing a real Kind afterwards drops the marker, so the item is normal again.
  ev(`w0.value="polo"; w0.onchange();`);
  const retyped = ev(`sheet.item`);
  check("picking a Kind again drops the cleared marker",
    retyped.type === "polo" && !retyped.typeCleared, retyped);

  // The case the reviewer caught: an item that simply never got a Kind is NOT a
  // decision, and must stay eligible for the re-scan.
  const offline = ev(`reconcileItem({id:"x5",label:"navy merino crew-neck",category:"base",group:"tops",count:1,photo:true})`);
  check("an item reconciled without a Kind is not treated as a deliberate blank",
    !offline.typeCleared, offline);

  console.log("\n--- 11. specific beats generic, by table not by accident -------");
  /* Character length is not specificity. Scoring by it filed "Navy polo shirt" as
     a plain shirt, because "shirt" has one more character than "polo" — and that
     is one of the commonest labels in the closet. Raised by the pre-push reviewer,
     2026-08-23. */
  const PREFER = [
    ["Navy polo shirt",      "tops", "polo"],
    ["Polo shirt",           "tops", "polo"],
    ["Grey v-neck t-shirt",  "tops", "t_shirt"],
    ["White dress shirt",    "tops", "shirt"],     // a dress shirt IS a shirt
    ["Knit cardigan",        "tops", "cardigan"],  // beats sweater's "knit"
    ["Hooded sweatshirt",    "tops", "hoodie"],
    ["Down puffer jacket",   "outerwear", "puffer"],
    ["Rain jacket",          "outerwear", "rainwear"],
    ["Navy suit jacket",     "outerwear", "blazer"],
    ["Blue denim jacket",    "outerwear", "jacket"],
    ["Black skinny jeans",   "bottoms", "jeans"],
  ];
  for (const [label, grp, want] of PREFER)
    check(`"${label}" files as ${want}`,
      ev(`typeFromLabel(${JSON.stringify(label)},${JSON.stringify(grp)})`) === want,
      ev(`typeFromLabel(${JSON.stringify(label)},${JSON.stringify(grp)})`));

  // The self-guard: a type added to TYPES with no place in the precedence table
  // would rank `undefined` and lose every tie silently. Fail here instead.
  const everyType = ev(`Object.values(TYPES).flat()`);
  const ranked = ev(`TYPE_PRECEDENCE`);
  check("every type has a precedence entry",
    everyType.every(t => ranked.includes(t)),
    everyType.filter(t => !ranked.includes(t)));
  check("and the table invents none that do not exist",
    ranked.every(t => everyType.includes(t)),
    ranked.filter(t => !everyType.includes(t)));
  check("each exactly once", ranked.length === new Set(ranked).size && ranked.length === everyType.length,
    { table: ranked.length, types: everyType.length });

  console.log("\n--- 12. re-reading the KIND off the photo (2026-08-23) ----------");
  /* typeFromLabel can only go as far as the words. The classifier is asked for
     "short item name a person would say" and obliges — "navy merino crew-neck" —
     so most real labels name no garment at all and the item stays under "Other".
     The photo is the only place the answer actually is. */
  ev(`closet=[
    {id:"r1",label:"navy merino crew-neck",category:"base",group:"tops",count:1,photo:true},
    {id:"r2",label:"grey v-neck",category:"base",group:"tops",count:1,photo:true},
    {id:"r3",label:"Navy polo",category:"base",group:"tops",type:"polo",count:1,photo:true},
    {id:"r4",label:"cleared on purpose",category:"base",group:"tops",typeCleared:true,count:1,photo:true},
    {id:"r5",label:"no photo",category:"base",group:"tops",count:1,photo:false}];`);
  const pending = ev(`untypedItems().map(i=>i.id)`);
  check("only items with no Kind AND a photo are offered", 
    JSON.stringify(pending) === '["r1","r2"]', pending);
  check("an explicitly cleared Kind is left alone", !pending.includes("r4"), pending);
  check("and an item with no photo cannot be re-read", !pending.includes("r5"), pending);

  ev(`refreshRescan()`);
  check("the control appears when there is something to identify",
    w.document.getElementById("rescanRow").style.display !== "none");
  check("and says how many", /Identify 2 items/.test(w.document.getElementById("rescanTxt").textContent),
    w.document.getElementById("rescanTxt").textContent);

  // The re-scan must fill the Kind and touch NOTHING the user may have corrected.
  ev(`photoLoad = async () => "data:image/jpeg;base64,AAAA";`);
  ev(`classifyPhoto = async () => ({label:"REPLACED", category:"outer", group:"tops",
       type:"sweater", colors:["red"], warmth:5, formality:["smart"], waterproof:true});`);
  await ev(`rescanTypes()`);
  const r1 = ev(`closet.find(i=>i.id==="r1")`);
  check("the Kind is filled in from the photo", r1.type === "sweater", r1);
  check("the label the user may have edited is NOT replaced",
    r1.label === "navy merino crew-neck", r1.label);
  check("nor the colours", JSON.stringify(r1.colors || []) !== '["red"]', r1.colors);
  check("nor the warmth", r1.warmth !== 5, r1.warmth);
  const r3 = ev(`closet.find(i=>i.id==="r3")`);
  check("an item that already had a Kind is not re-scanned at all",
    r3.type === "polo" && r3.label === "Navy polo", r3);
  const r4 = ev(`closet.find(i=>i.id==="r4")`);
  check("and neither is one whose Kind was deliberately cleared",
    !r4.type, r4);
  ev(`refreshRescan()`);
  check("the control disappears once nothing is left to identify",
    w.document.getElementById("rescanRow").style.display === "none",
    w.document.getElementById("rescanRow").style.display);

  // A dead server must not silently blank the closet.
  ev(`closet=[{id:"r6",label:"navy merino crew-neck",category:"base",group:"tops",count:1,photo:true}];`);
  ev(`classifyPhoto = async () => null;`);
  await ev(`rescanTypes()`);
  const r6 = ev(`closet.find(i=>i.id==="r6")`);
  check("an unreachable advisor leaves the item exactly as it was",
    !r6.type && r6.label === "navy merino crew-neck", r6);
  check("and says so rather than claiming success",
    /Couldn't identify/.test(w.document.getElementById("rescanNote").textContent),
    w.document.getElementById("rescanNote").textContent);

  console.log("\n--- 13. the control exists on a COLD START ----------------------");
  /* The whole point of the re-scan is the closet that is already on the phone, so
     it has to be there when the app is merely opened. It was wired to saveCloset
     only, which meant a user with a legacy closet had to perform some unrelated
     write before the recovery action would appear at all. Raised by the pre-push
     reviewer, 2026-08-23. */
  w.localStorage.setItem("oa.closet", JSON.stringify([
    {id:"c1",label:"navy merino crew-neck",category:"base",group:"tops",count:1,photo:true,
     colors:[],warmth:3,formality:["casual"],waterproof:false}]));
  w.document.getElementById("rescanRow").style.display = "none";   // as a fresh page would be
  await ev(`load()`);
  ev(`renderCloset(); refreshRescan();`);
  check("a closet loaded from storage with no Kinds offers the re-scan",
    w.document.getElementById("rescanRow").style.display !== "none",
    w.document.getElementById("rescanRow").style.display);
  // And the init path itself must call it, not just this test.
  const src = fs.readFileSync(HTML, "utf8");
  const init = src.slice(src.indexOf("const appReady="));
  check("init refreshes the control, so opening the app is enough",
    /refreshRescan\(\)/.test(init.slice(0, init.indexOf("})();"))), "not called in init");

  console.log("\n--- 14. appReady means PAINTED, not merely loaded ---------------");
  /* renderCloset reads a photo per item off disk, so it is async. If init does not
     await it, appReady resolves with the grid still pending and the initial render
     lands AFTER a caller has already drawn its own — silently replacing it. Raised
     by the pre-push reviewer, 2026-08-23. */
  const src2 = fs.readFileSync(HTML, "utf8");
  const initBody = src2.slice(src2.indexOf("const appReady="));
  check("init awaits the closet render before resolving",
    /await renderCloset\(\)/.test(initBody.slice(0, initBody.indexOf("})();"))),
    "renderCloset is not awaited in init");

  // Behavioural: a slow photo read must not let the initial render clobber a later one.
  w.localStorage.setItem("oa.closet", JSON.stringify([
    {id:"s1",label:"Navy polo",category:"base",group:"tops",type:"polo",count:1,photo:true,
     colors:[],warmth:2,formality:["casual"],waterproof:false}]));
  ev(`photoLoad = async (id) => { await new Promise(r=>setTimeout(r,25));
        return "data:image/jpeg;base64,AAAA"; };`);
  await ev(`load()`);
  await ev(`renderCloset()`);
  ev(`closet=[{id:"s2",label:"Blue jeans",category:"bottoms",group:"bottoms",type:"jeans",count:1,photo:false,
              colors:[],warmth:2,formality:["casual"],waterproof:false}];`);
  await ev(`renderCloset()`);
  await new Promise(r => setTimeout(r, 60));   // let any stale render land if it can
  check("the newest render is the one on screen",
    w.document.querySelectorAll('.item[data-id="s2"]').length === 1 &&
    w.document.querySelectorAll('.item[data-id="s1"]').length === 0,
    w.document.getElementById("closetGrid").innerHTML.slice(0, 200));

  console.log("\n--- replacing a garment's picture (2026-08-31) -------------------");
  /* User: "some of my trousers pictures are difficult to tell which is which as I
     took a picture of the trousers being folded — prefer to retake and upload."

     A name is not how anybody recognises their own clothes; the photo is, which is
     why the outfit card leads with pictures. A bad photo is therefore not untidy,
     it is a garment gone unidentifiable in its own wardrobe. Until today the sheet
     could change every field EXCEPT the one that matters most: photoSave ran for
     new items only, so a retake was captured, previewed, saved — and dropped. */
  const stub = `capture=async()=>"data:image/jpeg;base64,NEWPHOTO";
                downscale=async(d)=>d.split(",")[1];`;
  const TROUSERS = {id:"itm-trs-0001", label:"grey wool trousers", category:"bottoms",
    group:"bottoms", type:"trousers", roles:["bottoms"], colors:["grey"], warmth:3,
    formality:["smart"], waterproof:false, count:1, photo:true};
  ev(`closet=[${JSON.stringify(TROUSERS)}]; ${stub}`);
  w.localStorage.setItem("oa.photo.itm-trs-0001", "OLDPHOTO");
  ev(`photoLoad=async(id)=>{ const d=localStorage.getItem("oa.photo."+id);
        return d?"data:image/jpeg;base64,"+d:null; };
      photoSave=async(id,b64)=>{ localStorage.setItem("oa.photo."+id,b64); return true; };`);

  await ev(`openSheet(closet[0],{isNew:false})`);
  check("the sheet opens on the picture it has",
    /OLDPHOTO/.test(w.document.getElementById("shImg").src),
    w.document.getElementById("shImg").src.slice(0, 60));
  check("and the placeholder stays out of the way",
    w.document.getElementById("shNoPic").style.display === "none");

  await ev(`replacePhoto("CAMERA")`);
  check("retaking shows the new picture at once",
    /NEWPHOTO/.test(w.document.getElementById("shImg").src),
    w.document.getElementById("shImg").src.slice(0, 60));
  /* Nothing is written until Save. The photo is the one field with no undo — the
     original is gone from the camera roll as often as not — so a retake thought
     better of, or a sheet dismissed by the back gesture, must leave it alone. */
  check("but nothing is written yet",
    w.localStorage.getItem("oa.photo.itm-trs-0001") === "OLDPHOTO",
    w.localStorage.getItem("oa.photo.itm-trs-0001"));
  ev(`closeSheet()`);
  check("and dismissing the sheet keeps the old picture",
    w.localStorage.getItem("oa.photo.itm-trs-0001") === "OLDPHOTO",
    w.localStorage.getItem("oa.photo.itm-trs-0001"));

  await ev(`openSheet(closet[0],{isNew:false})`);
  await ev(`replacePhoto("PHOTOS")`);
  await ev(`document.getElementById("shSave").onclick()`);
  check("saving replaces the picture, under the same garment",
    w.localStorage.getItem("oa.photo.itm-trs-0001") === "NEWPHOTO",
    w.localStorage.getItem("oa.photo.itm-trs-0001"));
  check("the garment is the same one, not a second copy",
    ev(`closet.length`) === 1 && ev(`closet[0].id`) === "itm-trs-0001", ev(`closet.length`));
  check("and it now says it has a photo", ev(`closet[0].photo`) === true);

  /* Backing out of the camera is not an error, and must not disturb what is there. */
  await ev(`openSheet(closet[0],{isNew:false})`);
  ev(`capture=async()=>{ throw new Error("User cancelled photos app"); };`);
  await ev(`replacePhoto("CAMERA")`);
  check("cancelling the camera leaves the picture as it was",
    /NEWPHOTO/.test(w.document.getElementById("shImg").src) && ev(`sheet.b64`) === null,
    w.document.getElementById("shImg").src.slice(0, 60));
  ev(stub);

  /* A garment with no picture at all — the placeholder is what makes the buttons
     under it read as "add one" rather than as part of the name field. */
  ev(`closet=[{...closet[0], id:"itm-trs-0002", photo:false}];`);
  await ev(`openSheet(closet[0],{isNew:false})`);
  check("a garment with no picture shows a placeholder, not a hole",
    w.document.getElementById("shNoPic").style.display === "flex" &&
    w.document.getElementById("shImg").style.display === "none",
    w.document.getElementById("shNoPic").style.display);
  await ev(`replacePhoto("CAMERA")`);
  await ev(`document.getElementById("shSave").onclick()`);
  check("and giving it one works the same way",
    w.localStorage.getItem("oa.photo.itm-trs-0002") === "NEWPHOTO" &&
    ev(`closet.find(i=>i.id==="itm-trs-0002").photo`) === true,
    w.localStorage.getItem("oa.photo.itm-trs-0002"));

  /* The camera is another app, and it can outlive the sheet that opened it. A
     wearer who dismisses that sheet and opens a different garment must not get the
     first garment's photograph written onto the second. Raised by the pre-push
     reviewer, 2026-08-31. */
  ev(`closet=[${JSON.stringify(TROUSERS)},
              {...${JSON.stringify(TROUSERS)}, id:"itm-trs-0003", label:"black jeans"}];`);
  w.localStorage.setItem("oa.photo.itm-trs-0001", "OLDPHOTO");
  w.localStorage.setItem("oa.photo.itm-trs-0003", "JEANSPHOTO");
  ev(`__release=null;
      capture=()=>new Promise(r=>{ __release=()=>r("data:image/jpeg;base64,STRAY"); });`);
  await ev(`openSheet(closet[0],{isNew:false})`);
  const inCamera = ev(`replacePhoto("CAMERA")`);        // still in the camera
  ev(`closeSheet()`);
  await ev(`openSheet(closet[1],{isNew:false})`);        // a different garment
  ev(`__release()`);
  await inCamera;
  check("a photo from a dismissed sheet does not land on the next garment",
    ev(`sheet.b64`) === null, ev(`String(sheet.b64).slice(0,20)`));
  await ev(`document.getElementById("shSave").onclick()`);
  check("so saving that garment keeps its own picture",
    w.localStorage.getItem("oa.photo.itm-trs-0003") === "JEANSPHOTO",
    w.localStorage.getItem("oa.photo.itm-trs-0003"));
  check("and the garment it was meant for is untouched too",
    w.localStorage.getItem("oa.photo.itm-trs-0001") === "OLDPHOTO",
    w.localStorage.getItem("oa.photo.itm-trs-0001"));
  ev(stub);

  /* A write that cannot be read back is a write that did not happen. photoLoad
     reads the filesystem before localStorage, so on a device where the filesystem
     write fails and the fallback succeeds, every screen would go on loading the OLD
     picture while Save reported success. And a failed write must never clear the
     flag on a garment whose old picture is still perfectly there. */
  ev(`closet=[${JSON.stringify(TROUSERS)}];`);
  w.localStorage.setItem("oa.photo.itm-trs-0001", "OLDPHOTO");
  ev(`photoSave=async()=>false;`);          // stored nothing that can be read back
  await ev(`openSheet(closet[0],{isNew:false})`);
  await ev(`replacePhoto("CAMERA")`);
  await ev(`document.getElementById("shSave").onclick()`);
  check("a picture that cannot be stored leaves the old one in place",
    w.localStorage.getItem("oa.photo.itm-trs-0001") === "OLDPHOTO",
    w.localStorage.getItem("oa.photo.itm-trs-0001"));
  check("and does NOT un-picture a garment that still has one",
    ev(`closet[0].photo`) === true, ev(`String(closet[0].photo)`));
  check("the wearer is told, rather than left believing it worked",
    /could not be stored/.test(w.document.getElementById("toast").textContent),
    w.document.getElementById("toast").textContent);

  /* And the read-back itself: a stale filesystem copy shadowing the fallback is the
     exact failure, so photoSave must answer for what photoLoad will find. Run on a
     FRESH page, because the assertions above replaced both functions. */
  const wP = page2();
  await wP.eval("appReady");
  wP.eval(`localStorage.setItem("oa.photo.itm-shadow-1","OLD");`);
  const ep = (c) => wP.eval(c);
  check("a write that reads back as itself is a success",
    (await ep(`photoSave("itm-shadow-1","NEW")`)) === true &&
    wP.localStorage.getItem("oa.photo.itm-shadow-1") === "NEW",
    wP.localStorage.getItem("oa.photo.itm-shadow-1"));
  /* The shadow, exactly: the write lands somewhere, and the reader finds something
     else. Nothing about the write returning tells you that. */
  ep(`photoLoad=async()=>"data:image/jpeg;base64,SOMETHINGELSE";`);
  check("a write the reader would not find is reported as a failure",
    (await ep(`photoSave("itm-shadow-1","NEWER")`)) === false);

  /* The device case in full, which is the only place it can happen: the filesystem
     write fails, the localStorage fallback succeeds — and photoLoad reads the
     filesystem FIRST, so the file already sitting there would hand back the old
     picture for ever while Save reported success. */
  const wF = page2();
  await wF.eval("appReady");
  wF.eval(`__fs={deleted:false};
    Plugins.Filesystem={
      writeFile:async()=>{ throw new Error("no space left on device"); },
      deleteFile:async()=>{ __fs.deleted=true; },
      readFile:async()=>{ if(__fs.deleted) throw new Error("not found");
                          return {data:"FOLDEDTROUSERS"}; } };`);
  const stored = await wF.eval(`photoSave("itm-trs-0001","RETAKEN")`);
  check("a failed filesystem write does not leave the old file shadowing the new one",
    stored === true && wF.eval(`__fs.deleted`) === true &&
    wF.localStorage.getItem("oa.photo.itm-trs-0001") === "RETAKEN",
    { stored, deleted: wF.eval(`__fs.deleted`) });
  /* The mirror of the shadow: the filesystem write SUCCEEDS while an older copy is
     still sitting in localStorage. Left there, it resurfaces the moment a filesystem
     read fails or the app runs without the plugin — the replacement appearing to
     revert, weeks later, for no reason the wearer can see. Raised by the pre-push
     reviewer, 2026-08-31. */
  const wH = page2();
  await wH.eval("appReady");
  wH.localStorage.setItem("oa.photo.itm-trs-0001", "FOLDEDTROUSERS");
  wH.eval(`__file=null;
    Plugins.Filesystem={
      writeFile:async(o)=>{ __file=o.data; },
      deleteFile:async()=>{ __file=null; },
      readFile:async()=>{ if(__file===null) throw new Error("not found");
                          return {data:__file}; } };`);
  check("a filesystem replacement reports success",
    (await wH.eval(`photoSave("itm-trs-0001","RETAKEN")`)) === true);
  check("and takes the older fallback copy with it",
    wH.localStorage.getItem("oa.photo.itm-trs-0001") === null,
    wH.localStorage.getItem("oa.photo.itm-trs-0001"));
  wH.eval(`Plugins.Filesystem.readFile=async()=>{ throw new Error("unreadable"); };`);
  check("so a filesystem that stops answering cannot resurrect the old picture",
    (await wH.eval(`photoLoad("itm-trs-0001")`)) === null,
    await wH.eval(`photoLoad("itm-trs-0001")`));

  /* A write that RETURNS is not a write that landed. When the read-back cannot find
     the new picture, the fallback underneath is the only copy there is — dropping it
     on the strength of a write that merely did not throw would delete the last one. */
  const wI = page2();
  await wI.eval("appReady");
  wI.localStorage.setItem("oa.photo.itm-trs-0001", "THEONLYCOPY");
  wI.eval(`Plugins.Filesystem={
      writeFile:async()=>{},                       // returns, stores nothing
      deleteFile:async()=>{},
      readFile:async()=>{ throw new Error("not there after all"); } };`);
  check("a write that cannot be read back is a failure",
    (await wI.eval(`photoSave("itm-trs-0001","RETAKEN")`)) === false);
  check("and the copy underneath is left alone, being the only one",
    wI.localStorage.getItem("oa.photo.itm-trs-0001") === "THEONLYCOPY",
    wI.localStorage.getItem("oa.photo.itm-trs-0001"));

  /* And when BOTH stores fail, the old picture must survive. Deleting the file
     before discovering the fallback cannot take it destroyed a photograph the
     wearer may have no way to take again — the failure path promises to leave it
     intact, and that promise is the whole reason nothing is written until Save.
     Raised by the pre-push reviewer, 2026-08-31. */
  const wG = page2();
  await wG.eval("appReady");
  wG.eval(`__g={deleted:false};
    Plugins.Filesystem={
      writeFile:async()=>{ throw new Error("no space left on device"); },
      deleteFile:async()=>{ __g.deleted=true; },
      readFile:async()=>{ if(__g.deleted) throw new Error("not found");
                          return {data:"THEONLYCOPY"}; } };`);
  // On the PROTOTYPE: jsdom's Storage ignores an own-property override, so an
  // assignment here would have made this test pass against a broken ordering.
  wG.eval(`__setItem=Object.getPrototypeOf(localStorage).setItem;
           Object.getPrototypeOf(localStorage).setItem=()=>{
             throw new Error("QuotaExceededError"); };`);
  const both = await wG.eval(`photoSave("itm-trs-0001","RETAKEN")`);
  wG.eval(`Object.getPrototypeOf(localStorage).setItem=__setItem;`);
  check("when nothing can store the new picture, the old one is not deleted",
    both === false && wG.eval(`__g.deleted`) === false, { both, deleted: wG.eval(`__g.deleted`) });
  check("and it is still what the reader finds",
    (await wG.eval(`photoLoad("itm-trs-0001")`)) === "data:image/jpeg;base64,THEONLYCOPY",
    await wG.eval(`photoLoad("itm-trs-0001")`));

  check("and the reader now finds the retaken picture",
    (await wF.eval(`photoLoad("itm-trs-0001")`)) === "data:image/jpeg;base64,RETAKEN",
    await wF.eval(`photoLoad("itm-trs-0001")`));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
