/**
 * brand.test.js — the Brand field and "Read brands from the photos" (user,
 * 2026-09-30: "add Brand field for each of the items in closet ... scan through the
 * pictures and fill Brand field").
 *
 * Pinned:
 *   - the scan fills `brand` and NOTHING else, "" where the photo showed no maker,
 *     and does not ask about an item twice;
 *   - it stops when the advisor is unreachable, leaving the rest unread;
 *   - the edit sheet shows and saves the brand, and saving an unrelated edit on a
 *     never-scanned item does not take it out of the scan;
 *   - the tile shows the brand.
 *
 * Loads the REAL app/www/index.html in jsdom; photos land in localStorage there.
 * Run: npm test   (or: node tests/brand.test.js)
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

const PHOTO = "P".repeat(200);
const item = (id, label, extra = {}) => ({id, label, category: "base", group: "tops", type: "t_shirt",
  roles: ["base"], colors: ["navy"], warmth: 2, formality: ["casual"], waterproof: false, count: 1,
  photo: true, ...extra});
const answer = brand => ({label: "SHOULD NOT BE USED", group: "outerwear", type: "parka",
  category: "outer", roles: ["outer"], colors: ["red"], warmth: 5, formality: ["smart"],
  waterproof: true, brand});

(async () => {
  console.log("\n--- 1. the scan -----------------------------------------------------");
  const w = page();
  await w.eval("appReady");
  await w.eval(`closet=[${JSON.stringify(item("b1", "navy tee"))}, ${JSON.stringify(item("b2", "grey tee"))},
    ${JSON.stringify(item("b3", "white tee", {brand: "Muji"}))},
    ${JSON.stringify(item("b4", "black tee", {photo: false}))}]; saveCloset()`);
  for (const id of ["b1", "b2", "b3"]) w.localStorage.setItem("oa.photo." + id, PHOTO);
  w.eval("refreshBrands()");
  const row = w.document.getElementById("brandRow");
  check("the row offers only photographed items with no brand read yet",
    row.style.display !== "none" && /2 photos/.test(w.document.getElementById("brandTxt").textContent),
    w.document.getElementById("brandTxt").textContent);

  const asked = [];
  w.fetch = async (url, opts) => {
    asked.push(url);
    const n = asked.length;
    return {ok: true, status: 200, json: async () => answer(n === 1 ? "Uniqlo" : null)};
  };
  await w.eval("scanBrands()");
  const c = JSON.parse(w.eval("JSON.stringify(closet)"));
  const by = id => c.find(i => i.id === id);
  check("a legible brand is filled in", by("b1").brand === "Uniqlo", by("b1"));
  check("no legible brand is recorded as read-and-empty", by("b2").brand === "", by("b2"));
  check("an existing brand is left alone and not re-asked", by("b3").brand === "Muji" && asked.length === 2, asked);
  check("an item without a photo is not asked", by("b4").brand === undefined);
  check("nothing but the brand is touched",
    by("b1").label === "navy tee" && by("b1").type === "t_shirt" && by("b1").warmth === 2
    && by("b1").waterproof === false && by("b1").colors[0] === "navy", by("b1"));
  const stored = JSON.parse(await w.eval(`prefGet("oa.closet","[]")`));
  check("it is persisted", stored.find(i => i.id === "b1")?.brand === "Uniqlo", stored);
  check("the result says how many were found",
    /Found a brand on 1 of 2/.test(w.document.getElementById("brandNote").textContent),
    w.document.getElementById("brandNote").textContent);
  await w.eval("scanBrands()");
  check("a second tap asks nothing again", asked.length === 2, asked.length);

  console.log("\n--- 2. unreachable -------------------------------------------------");
  await w.eval(`closet=[${JSON.stringify(item("u1", "tee one"))}, ${JSON.stringify(item("u2", "tee two"))}]; saveCloset()`);
  for (const id of ["u1", "u2"]) w.localStorage.setItem("oa.photo." + id, PHOTO);
  let calls = 0;
  w.fetch = async () => { calls++; throw new TypeError("Failed to fetch"); };
  await w.eval("scanBrands()");
  const u = JSON.parse(w.eval("JSON.stringify(closet)"));
  check("it stops at the first failure", calls === 1, calls);
  check("nothing is marked read", u.every(i => i.brand === undefined), u.map(i => i.brand));
  check("the row still offers them", w.document.getElementById("brandRow").style.display !== "none");

  console.log("\n--- 3. the edit sheet and the tile ------------------------------------");
  await w.eval(`closet=[${JSON.stringify(item("s1", "navy tee"))}, ${JSON.stringify(item("s2", "grey tee", {brand: "Gap"}))}]; saveCloset()`);
  await w.eval(`openSheet(closet[0],{isNew:false})`); await drain();
  check("an unread item opens with an empty Brand", w.document.getElementById("shBrand").value === "");
  w.document.getElementById("shLabel").value = "navy crew tee";
  await w.document.getElementById("shSave").onclick(); await drain();
  let s = JSON.parse(w.eval("JSON.stringify(closet)"));
  check("saving another edit leaves it in the scan", s[0].label === "navy crew tee" && s[0].brand === undefined, s[0]);

  await w.eval(`openSheet(closet[1],{isNew:false})`); await drain();
  check("a known brand is shown in the sheet", w.document.getElementById("shBrand").value === "Gap");
  w.document.getElementById("shBrand").value = "  Banana Republic ";
  await w.document.getElementById("shSave").onclick(); await drain();
  s = JSON.parse(w.eval("JSON.stringify(closet)"));
  check("a typed brand is saved, trimmed", s[1].brand === "Banana Republic", s[1]);

  await w.eval(`openSheet(closet[1],{isNew:false})`); await drain();
  w.document.getElementById("shBrand").value = "";
  await w.document.getElementById("shSave").onclick(); await drain();
  s = JSON.parse(w.eval("JSON.stringify(closet)"));
  check("clearing a brand records no-brand, not unread", s[1].brand === "", s[1]);

  await w.eval(`closet=[${JSON.stringify(item("t1", "navy tee", {brand: "A.P.C. <b>x</b>"}))}]; saveCloset()`);
  await w.eval("renderCloset()"); await drain();
  const html = w.document.body.innerHTML;
  check("the tile shows the brand, escaped", html.includes("A.P.C. &lt;b&gt;x&lt;/b&gt;") && !html.includes("<b>x</b>"));

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
