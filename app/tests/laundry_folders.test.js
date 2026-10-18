/**
 * laundry_folders.test.js — "What's still in the laundry?" in the Closet tab's folders
 * (user, 2026-10-18: "What's still in laundry is difficult to see. Can you make it
 * easier to sort by adding grouping the expand collapse possibility? Grouping shall be
 * the same as closet").
 *
 * Pinned:
 *   - the same folders, order and labels as the Closet tab, then the same kinds;
 *   - a folder opens and folds; on opening, only folders with something waiting are open;
 *   - a tick inside a folded folder stands and is saved; the folder counts what waits;
 *   - shoes and accessories stay out (never washed), socks stay in;
 *   - a kind outside the vocabulary is listed under "Other", never dropped.
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

const item = (id, label, category, group, type, extra = {}) => ({id, label, category, group, type,
  roles: [category], colors: ["navy"], warmth: 2, formality: ["casual"], waterproof: false, count: 1, ...extra});
const CLOSET = [
  item("jeans", "dark jeans", "bottoms", "bottoms", "jeans"),
  item("polo", "navy polo", "base", "tops", "polo"),
  item("tee", "white tee", "base", "tops", "t_shirt", {count: 3}),
  item("sweat", "grey sweater", "mid", "tops", "sweater"),
  item("odd", "linen kurta", "base", "tops", "kurta"),
  item("shoe", "grey sneakers", "footwear", "footwear", "sneakers"),
  item("sock", "black socks", "footwear", "footwear", "socks", {count: 4}),
  item("belt", "navy belt", "accessories", "accessories", "belt"),
];

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const T = w.Date.now();
  w.Date.now = () => T;
  const $ = id => w.document.getElementById(id);
  const heads = sel => [...w.document.querySelectorAll(`${sel} .folderHead`)].map(b => b.dataset.grp);
  const head = g => w.document.querySelector(`#dirtyList .folderHead[data-grp="${g}"]`);
  const body = g => head(g).parentElement.querySelector(".dirtyBody");
  const open = async () => { $("dirtyBtn").onclick(); await drain(); };

  await ev(`closet=${JSON.stringify(CLOSET)}; wearLog=[{itemId:"jeans",wornAt:${T - 86400000}}];
    lastWorn={}; closetFolded=new Set(); saveCloset()`);
  await drain(); await ev("renderCloset()"); await drain();

  console.log("\n--- 1. the Closet tab's folders ------------------------------------");
  await open();
  const closetHeads = heads("#closetGrid").filter(g => !["accessories"].includes(g));
  check("the same folders in the same order as the Closet tab (bar accessories)",
    JSON.stringify(heads("#dirtyList")) === JSON.stringify(closetHeads), [heads("#dirtyList"), closetHeads]);
  check("with the Closet tab's labels", head("base").textContent.includes(ev(`LABELS.base`)));
  const kinds = [...body("base").querySelectorAll(".subHead .st")].map(e => e.textContent);
  check("then its kinds, in its order", JSON.stringify(kinds) === JSON.stringify(["T-shirt", "Polo shirt", "Other"]),
    kinds);
  check("a kind outside the vocabulary is under Other, not dropped",
    !!body("base").querySelector('[data-id="odd"]'));
  check("each row still says which load it goes in", head("bottoms").parentElement.textContent.includes("Darks"));

  console.log("\n--- 2. what is never washed stays out ------------------------------");
  check("sneakers and the belt are not listed",
    !w.document.querySelector('#dirtyList [data-id="shoe"]') && !w.document.querySelector('#dirtyList [data-id="belt"]'));
  check("socks are, in Footwear", !!body("footwear").querySelector('[data-id="sock"]'));
  check("no Accessories folder at all", !head("accessories"));

  console.log("\n--- 3. open and folded -------------------------------------------");
  check("the folder with something waiting opens", !body("bottoms").hidden && head("bottoms").textContent.includes("1 waiting"));
  check("the others start folded", body("base").hidden && body("mid").hidden && body("footwear").hidden);
  check("…and say so", head("base").textContent.includes("▸") && head("bottoms").textContent.includes("▾"));
  head("base").onclick(); await drain();
  check("a tap opens a folder", !body("base").hidden && head("base").getAttribute("aria-expanded") === "true");
  const box = id => w.document.querySelector(`#dirtyList input[data-id="${id}"]`);
  box("polo").checked = true; box("polo").onchange();
  check("its count follows a tick", head("base").textContent.includes("1 waiting"));
  head("base").onclick(); await drain();
  check("a second tap folds it", body("base").hidden);
  check("the tick inside the folded folder stands", box("polo").checked);
  await $("dirtySave").onclick(); await drain();
  check("…and is saved", ev(`avail(closet.find(i=>i.id==="polo"))`) === 0);

  console.log("\n--- 4. reopening starts from what is waiting ---------------------");
  await open();
  check("base and bottoms open, the rest folded",
    !body("base").hidden && !body("bottoms").hidden && body("mid").hidden && body("footwear").hidden);
  $("dirtyCancel").onclick();

  console.log("\n--- 4b. a load's name is text, never markup -----------------------");
  await ev(`laundry.loads.find(l=>l.id==="dark").name="Darks <b>x</b>"`);
  await open();
  const note = head("bottoms").parentElement.querySelector(".note");
  check("shown as typed", note.textContent.includes("Darks <b>x</b>") && !note.querySelector("b"), note.innerHTML);
  $("dirtyCancel").onclick();

  console.log("\n--- 5. the Closet tab itself is unchanged ------------------------");
  const cKinds = [...w.document.querySelectorAll('#closetGrid .folderHead[data-grp="base"] ~ .subHead .st')]
    .map(e => e.textContent);
  check("its base folder has the same kinds", JSON.stringify(cKinds) === JSON.stringify(["T-shirt", "Polo shirt", "Other"]),
    cKinds);
  check("and lists the unknown kind too", !!w.document.querySelector('#closetGrid [data-id="odd"]'));

  console.log(`\nlaundry_folders: ${passed} passed, ${failed} failed`);
  if (failed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
