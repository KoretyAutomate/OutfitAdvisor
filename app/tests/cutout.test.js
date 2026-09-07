/**
 * cutout.test.js — the garment alone on white (user, 2026-09-07: "the functionality
 * Indyx had, removing the background and making the picture nice").
 *
 * The server does the cutting; this is the phone's half. Pinned:
 *   - cutoutPhoto() reports the three outcomes apart: ok with a picture, the server
 *     saying no (nothing found / no model), and unreachable;
 *   - "Tidy photos" replaces an existing photo with the cutout and flags the item,
 *     keeps the original when the server finds nothing, and stops when the server
 *     cannot be reached — never losing a picture in any of the three;
 *   - the row shows only while there is something to tidy.
 *
 * Loads the REAL app/www/index.html in jsdom; photos land in localStorage there
 * (no Filesystem plugin), which is the same fallback path the app itself uses.
 *
 * Run: npm test   (or: node tests/cutout.test.js)
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

const ORIG = "T".repeat(200);   // a 'photo' — base64 is opaque to the app
const CUT = "C".repeat(200);
const item = (id, label) => ({id, label, category: "base", group: "tops", type: "t_shirt", roles: ["base"],
  colors: ["white"], warmth: 1, formality: ["casual"], waterproof: false, count: 1, dirty: 0, photo: true});

(async () => {
  console.log("\n--- 1. the three outcomes are told apart --------------------------");
  const w = page();
  await w.eval("appReady");
  w.fetch = async () => ({ok: true, status: 200, json: async () => ({imageB64: CUT})});
  let r = await w.eval(`cutoutPhoto("${ORIG}")`);
  check("a picture comes back as ok", r && r.ok === true && r.b64 === CUT, r);
  w.fetch = async () => ({ok: false, status: 502, json: async () => ({})});
  r = await w.eval(`cutoutPhoto("${ORIG}")`);
  check("the server saying no is not ok, with its status", r && r.ok === false && r.status === 502, r);
  w.fetch = async () => { throw new TypeError("Failed to fetch"); };
  r = await w.eval(`cutoutPhoto("${ORIG}")`);
  check("unreachable is null", r === null, r);

  console.log("\n--- 2. Tidy photos ---------------------------------------------------");
  await w.eval(`closet=[${JSON.stringify(item("a1", "white tee"))}, ${JSON.stringify(item("a2", "grey tee"))},
    ${JSON.stringify({...item("a3", "navy tee"), cut: true})}]; saveCloset()`);
  w.localStorage.setItem("oa.photo.a1", ORIG);
  w.localStorage.setItem("oa.photo.a2", ORIG);
  w.localStorage.setItem("oa.photo.a3", CUT);
  w.eval("refreshTidy()");
  const row = w.document.getElementById("tidyRow");
  check("the row shows, counting only the photos not yet cut", row.style.display !== "none"
    && /Tidy 2 photos/.test(w.document.getElementById("tidyTxt").textContent), w.document.getElementById("tidyTxt").textContent);

  // first answers with a cutout, second: nothing found
  let calls = 0;
  w.fetch = async (url, opts) => {
    calls++;
    if (calls === 1) return {ok: true, status: 200, json: async () => ({imageB64: CUT})};
    return {ok: false, status: 502, json: async () => ({})};
  };
  await w.eval("tidyPhotos()");
  await drain();
  const cl = JSON.parse(w.eval("JSON.stringify(closet)"));
  check("the first photo is now the cutout and the item is flagged",
    w.localStorage.getItem("oa.photo.a1") === CUT && cl.find(i => i.id === "a1").cut === true);
  check("the second kept its original when nothing was found",
    w.localStorage.getItem("oa.photo.a2") === ORIG && !cl.find(i => i.id === "a2").cut);
  check("the already-cut one was not sent again", calls === 2, calls);
  check("the note says what happened", /Tidied 1 of 2/.test(w.document.getElementById("tidyNote").textContent),
    w.document.getElementById("tidyNote").textContent);

  console.log("\n--- 3. an unreachable server stops the run and loses nothing -------");
  w.fetch = async () => { throw new TypeError("Failed to fetch"); };
  await w.eval("tidyPhotos()");
  await drain();
  check("the original is still there", w.localStorage.getItem("oa.photo.a2") === ORIG);
  check("and the note says to come back", /stopped answering/.test(w.document.getElementById("tidyNote").textContent),
    w.document.getElementById("tidyNote").textContent);
  check("the row stays, since one photo is still untidy", w.document.getElementById("tidyRow").style.display !== "none");

  console.log("\n--- 4. nothing to tidy, no row -------------------------------------");
  await w.eval(`closet=[${JSON.stringify({...item("b1", "tee"), cut: true})}]; saveCloset()`);
  w.eval("refreshTidy()");
  check("the row hides when every photo is a cutout", w.document.getElementById("tidyRow").style.display === "none");

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
