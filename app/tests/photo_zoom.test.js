/**
 * photo_zoom.test.js — tap a picture to see it bigger (user, 2026-10-10): "I have a
 * few which looks similar and difficult to tell which is which".
 *
 * Pinned:
 *   - a tap on an outfit photo (tile or list thumbnail) opens the whole photo with
 *     the garment's brand and name; a tap anywhere closes it;
 *   - in the closet a tap still opens the garment, and press-and-hold shows the
 *     photo instead — without opening the garment as well;
 *   - the edit sheet's picture opens the viewer too;
 *   - a garment with no photo opens nothing.
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
const wait = ms => new Promise(r => setTimeout(r, ms));
const PHOTO = "P".repeat(200);
const item = (id, label, extra = {}) => ({id, label, category: "base", group: "tops", type: "t_shirt",
  roles: ["base"], colors: ["navy"], warmth: 2, formality: ["casual"], waterproof: false, count: 1,
  photo: true, ...extra});

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w.eval("appReady");
  const $ = id => w.document.getElementById(id);
  const open = () => $("zoomWrap").classList.contains("show");
  await w.eval(`closet=[${JSON.stringify(item("a", "navy tee", {brand: "Muji"}))},
    ${JSON.stringify(item("b", "black tee", {photo: false}))}]; saveCloset()`);
  w.localStorage.setItem("oa.photo.a", PHOTO);
  await w.eval("renderCloset()"); await drain();

  console.log("\n--- 1. outfit photos ------------------------------------------------");
  $("wearGrid").innerHTML = `<div class="wearIt" data-slot="base" data-pick="a"><img src="x" alt=""></div>`;
  $("wearGrid").querySelector("img").click(); await drain(); await drain();
  check("a tap on an outfit tile opens the viewer", open());
  check("…with the whole stored photo", $("zoomImg").src === "data:image/jpeg;base64," + PHOTO);
  check("…captioned with brand and name", /Muji/.test($("zoomCap").textContent)
    && /navy tee/.test($("zoomCap").textContent), $("zoomCap").textContent);
  $("zoomWrap").click();
  check("a tap anywhere closes it", !open());
  $("outfitList").innerHTML = `<li data-slot="base" data-pick="a"><span class="ic"><img class="thumb" src="x"></span></li>`;
  $("outfitList").querySelector("img").click(); await drain(); await drain();
  check("the list thumbnail opens it too", open());
  $("zoomWrap").click();
  $("outfitList").innerHTML = `<li data-slot="base" data-pick="b"><span class="ic"><img class="thumb" src="x"></span></li>`;
  $("outfitList").querySelector("img").click(); await drain(); await drain();
  check("a garment with no stored photo opens nothing", !open());

  console.log("\n--- 2. the closet: tap edits, hold enlarges -------------------------");
  const tile = $("closetGrid").querySelector('.item[data-id="a"]');
  check("the closet tile has its photo", !!(tile && tile.querySelector("img")));
  const img = tile.querySelector("img");
  const ptr = (t, type, x = 5, y = 5) => t.dispatchEvent(new w.MouseEvent(type, {bubbles: true, clientX: x, clientY: y}));
  ptr(img, "pointerdown"); ptr(img, "pointerup"); img.click(); await drain(); await drain();
  check("a short tap opens the garment, not the viewer",
    $("sheetWrap").classList.contains("show") && !open());
  w.eval("closeSheet()");
  ptr(img, "pointerdown"); await wait(520); await drain();
  check("press-and-hold opens the viewer", open());
  ptr(img, "pointerup"); img.click(); await drain();
  check("…and releasing does not open the garment as well", !$("sheetWrap").classList.contains("show"));
  $("zoomWrap").click();
  ptr(img, "pointerdown"); ptr(img, "pointermove", 60, 5); await wait(520);
  check("a hold that moves (scrolling) opens nothing", !open());
  ptr(img, "pointerup");
  img.click(); await drain(); await drain();
  check("the next ordinary tap still opens the garment", $("sheetWrap").classList.contains("show"));

  console.log("\n--- 3. the edit sheet ------------------------------------------------");
  $("shImg").click(); await drain();
  check("tapping the sheet's photo opens the viewer over it", open()
    && $("zoomImg").src === $("shImg").src, $("zoomImg").src.slice(0, 40));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
