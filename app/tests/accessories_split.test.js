/**
 * accessories_split.test.js — one accessory slot per body area (user, 2026-11-24:
 * "Accessories needs to be split. Belt and scarf can go together"). The server picks
 * (server/accessories.py); the phone's share is pinned here:
 *   - the twin tables agree with vocab.ACCESSORY_SLOTS and TYPE_DEFAULTS' roles;
 *   - a closet saved before v1.62 (category/roles "accessories") is filed by type;
 *   - old rules, swaps and shopping gaps are migrated on load;
 *   - the card draws the five, hides the folded line the server adds for older
 *     phones, lists only the accessories worn, and still draws the one generic line.
 *
 * Loads the REAL app/www/index.html in jsdom. Run: npm test
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
const VOCAB = fs.readFileSync(path.join(__dirname, "..", "..", "server", "vocab.py"), "utf8");
let passed = 0, failed = 0;
const check = (name, cond, detail = "") => {
  if (cond) { passed++; console.log(`[PASS] ${name}`); }
  else { failed++; console.log(`[FAIL] ${name}  ${JSON.stringify(detail)}`); }
};
const drain = () => new Promise(r => setTimeout(r, 0));
const J = v => JSON.stringify(v);

const BELT = {id: "belt00-0001", label: "brown belt", category: "accessories", group: "accessories", type: "belt",
  roles: ["accessories"], colors: ["brown"], warmth: 1, formality: ["casual"], waterproof: false, count: 1};
const SCARF = {...BELT, id: "scarf0-0001", label: "grey scarf", type: "scarf", colors: ["grey"], warmth: 4};

(async () => {
  // Saved state as v1.61 left it, read by the real boot.
  const saved = {
    "oa.closet": J([BELT, SCARF]),
    "oa.rules": J([
      {kind: "avoid_item", a: {role: "accessories", color: "red"}, text: "no red accessories"},
      {kind: "avoid_item", a: {role: "accessories", group: "tops"}, text: "odd"},
      {kind: "avoid_pair", a: {role: "accessories"}, b: {role: "accessories"}, text: "dead"},
      {kind: "avoid_item", a: {type: "t_shirt"}, text: "no tees"}]),
    "oa.swaps": J([{day: new Date().toISOString().slice(0, 10), slot: "accessories", wore: SCARF.id, instead: BELT.id},
                   {day: new Date().toISOString().slice(0, 10), slot: "accessories", wore: "gone00-0001", instead: ""},
                   {day: new Date().toISOString().slice(0, 10), slot: "base", wore: "x", instead: "y"}]),
    "oa.woreToday": J({day: new Date().toISOString().slice(0, 10), map: {base: "x", accessories: SCARF.id},
                       served: {base: "x", accessories: SCARF.id}}),
    "oa.gaps": J([{slot: "accessories", day: new Date().toISOString().slice(0, 10), lo: 2, hi: 8},
                  {slot: "umbrella", day: new Date().toISOString().slice(0, 10), lo: 2, hi: 8}]),
  };
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
    beforeParse(win) { for (const [k, v] of Object.entries(saved)) win.localStorage.setItem(k, v); },
  }).window;
  await w.eval("appReady");
  const ev = s => w.eval(s);

  console.log("\n--- the twin tables agree with server/vocab.py ---------------------");
  const py = VOCAB.match(/ACCESSORY_SLOTS = \(([^)]*)\)/)[1].match(/"(\w+)"/g).map(s => s.slice(1, -1));
  check("ACC_SLOTS is vocab.ACCESSORY_SLOTS", J(ev("ACC_SLOTS")) === J(py), [ev("ACC_SLOTS"), py]);
  check("CATS ends with the five", J(ev("CATS").slice(-5)) === J(py));
  for (const t of ["scarf", "gloves", "hat", "belt", "tie", "umbrella"]) {
    const m = VOCAB.match(new RegExp(`"${t}": \\{"roles": \\("(\\w+)",\\)`));
    check(`${t} plays the slot vocab gives it`, m && J(ev(`TYPE_ROLES.${t}`)) === J([m[1]]), [m && m[1], ev(`TYPE_ROLES.${t}`)]);
  }
  check("the accessories folder allows the five", J(ev("GROUP_CATS.accessories")) === J(py));

  console.log("\n--- a v1.61 closet is filed by type --------------------------------");
  const cl = JSON.parse(ev("JSON.stringify(closet)"));
  const of = id => cl.find(i => i.id === id) || {};
  check("the belt is in the belt slot", of(BELT.id).category === "belt" && J(of(BELT.id).roles) === J(["belt"]), of(BELT.id));
  check("the scarf is in the neck slot", of(SCARF.id).category === "neck" && J(of(SCARF.id).roles) === J(["neck"]), of(SCARF.id));
  check("an untyped accessory has one slot", J(JSON.parse(ev(
    `JSON.stringify(migrateItem(${J({...BELT, id: "untyp0-0001", label: "thing", type: null})}).roles)`))) === J(["neck"]));

  console.log("\n--- old rules, swaps and gaps --------------------------------------");
  const r = JSON.parse(ev("JSON.stringify(userRules)"));
  check("'no red accessories' bans red accessories", J(r[0].a) === J({color: "red", group: "accessories"}), r[0].a);
  check("a rule naming no accessory stays inert", r[1].a.role === "accessories", r[1].a);
  check("a pair of two accessories stays dead", ev("ruleIsDead(userRules[2])") === true, r[2]);
  check("other rules untouched", J(r[3].a) === J({type: "t_shirt"}));
  check("the red ban still bans a red belt", ev(`bannedOutright(${J({...BELT, category: "belt", roles: ["belt"], colors: ["red"]})})`) === true);
  check("and not a red shirt", ev(`bannedOutright(${J({...BELT, group: "tops", type: "shirt", category: "base", roles: ["base"], colors: ["red"]})})`) === false);
  const sw = JSON.parse(ev("JSON.stringify(swaps)"));
  check("a swap takes its garment's slot", sw.some(x => x.wore === SCARF.id && x.slot === "neck"), sw);
  check("a swap whose garment is gone is dropped", !sw.some(x => x.wore === "gone00-0001"), sw);
  check("other swaps untouched", sw.some(x => x.slot === "base"), sw);
  const gp = JSON.parse(ev("JSON.stringify(gaps)"));
  check("an old accessories gap is dropped", !gp.some(g => g.slot === "accessories"), gp);
  check("a body-area gap is kept", gp.some(g => g.slot === "umbrella"), gp);

  console.log("\n--- saved pick maps ------------------------------------------------");
  const wore = JSON.parse(ev("JSON.stringify(woreLogged)"));
  check("today's wear record moves the scarf to the neck slot", wore && wore.neck === SCARF.id && !("accessories" in wore), wore);
  check("and the served baseline too", JSON.parse(ev("JSON.stringify(woreServed)")).neck === SCARF.id);
  check("a garment that is gone is left where it was",
    J(JSON.parse(ev(`JSON.stringify(accPicks({accessories:"gone00-0001"}))`))) === J({accessories: "gone00-0001"}));
  const adv = JSON.parse(ev(`JSON.stringify(accAdvice({base:"oxford",accessories:"grey scarf"},{base:"x",accessories:${J(SCARF.id)}}))`));
  check("saved advice moves the scarf's line with its id",
    adv.picks.neck === SCARF.id && adv.outfit.neck === "grey scarf" && !("accessories" in adv.outfit), adv);
  ev("closetComplete=true");
  const kept = JSON.parse(ev(`JSON.stringify(closetOnlyView({outfit:${J(adv.outfit)},picks:${J(adv.picks)},text:""}))`));
  check("and closet-only keeps the owned scarf", kept.outfit.neck === "grey scarf", kept.outfit);
  const legacy = JSON.parse(ev(`JSON.stringify(closetOnlyView({outfit:{base:"oxford",accessories:"grey scarf (not in your closet yet)"},
    picks:{base:"x"},text:""}))`));
  check("closet-only empties a legacy generic accessory line", /^None/.test(legacy.outfit.accessories), legacy.outfit);
  ev("closetComplete=false; woreLogged=null; woreServed=null; woreEntry=null");   // the card shows the suggestion

  console.log("\n--- the outfit card ------------------------------------------------");
  const draw = (outfit, picks) => { ev(`drawOutfit(${J(outfit)},${J({picks, closetUsed: true})})`); };
  const clothes = {inner: "None needed", base: "oxford", mid: "None needed", outer: "coat", bottoms: "chinos",
    footwear: "loafers"};
  draw({...clothes, belt: "brown belt", neck: "grey scarf", head: "None needed", hands: "None needed",
    umbrella: "None needed", accessories: "brown belt, grey scarf", tip: ""},
    {base: "b", bottoms: "c", belt: BELT.id, neck: SCARF.id, accessories: BELT.id});   // the server's pick for older phones
  const tiles = [...w.document.querySelectorAll("#wearGrid .wearIt")].map(e => e.dataset.slot);
  const rows = [...w.document.querySelectorAll("#outfitList li")].map(e => e.dataset.slot);
  check("belt and scarf both get a tile", tiles.includes("belt") && tiles.includes("neck"), tiles);
  check("the folded line is not drawn twice", !tiles.includes("accessories") && !rows.includes("accessories"), [tiles, rows]);
  check("the list names every clothing slot", ["inner", "base", "mid", "outer", "bottoms", "footwear"].every(s => rows.includes(s)), rows);
  check("and only the accessories worn", rows.includes("belt") && rows.includes("neck") && !rows.includes("head")
    && !rows.includes("umbrella"), rows);
  draw({...clothes, accessories: "hat, gloves & scarf", tip: ""}, {});
  const gen = [...w.document.querySelectorAll("#outfitList li")].map(e => e.dataset.slot);
  check("a generic suggestion keeps its one accessories line", gen.includes("accessories")
    && !gen.some(s => ev("ACC_SLOTS").includes(s)), gen);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
