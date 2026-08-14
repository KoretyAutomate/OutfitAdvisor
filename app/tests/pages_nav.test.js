/**
 * pages_nav.test.js — three pages behind a gear (user, 2026-08-14).
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * What is worth pinning here is not that a div hides — it is WHICH CARD ENDED UP
 * ON WHICH PAGE. "Capture settings there" is only done if the settings are
 * actually behind the gear, and that is a property of the markup that a future
 * edit can undo silently: moving a card back to Today breaks nothing, renders
 * fine, and quietly puts the feature back where it started. So each control is
 * asserted against the page it lives on, by walking up from the element itself.
 *
 * Run: NODE_PATH=<...>/node_modules node tests/pages_nav.test.js
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

/** Which page an element sits on, read from the DOM rather than assumed. */
const pageOf = (id) => {
  const el = w.document.getElementById(id);
  const v = el && el.closest(".view");
  return v ? v.dataset.v : null;
};
const showing = (v) =>
  [...w.document.querySelectorAll(`.view[data-v="${v}"]`)].some(e => e.classList.contains("on"));

(async () => {
  for (let i = 0; i < 20 && !ev("state.baseUrl"); i++) await drain();
  await new Promise(r => setTimeout(r, 30));

  console.log("\n--- 1. the settings really are behind the gear --------------------");
  const SETTINGS = ["genderSeg", "styleSeg", "pushEnabled", "pushTime", "saveSchedule",
                    "readyList", "verLine", "baseUrl", "homeBtn", "homeLine"];
  for (const id of SETTINGS) check(`#${id} is on the settings page`, pageOf(id) === "settings", pageOf(id));
  check("the gear button exists and is in the header",
    !!w.document.querySelector("header #navSettings"));

  console.log("\n--- 2. the closet is its own page ---------------------------------");
  check("#closetGrid is on the closet page", pageOf("closetGrid") === "closet", pageOf("closetGrid"));
  check("so are the buttons that fill it",
    pageOf("addCamBtn") === "closet" && pageOf("laundryBtn") === "closet");
  check("the closet did not take the trips card with it",
    pageOf("calBtn") === "today", pageOf("calBtn"));
  check("today keeps what the app is FOR — the advice",
    pageOf("goBtn") === "today" && pageOf("outfitList") === "today" && pageOf("wxCard") === "today");

  console.log("\n--- 3. switching pages --------------------------------------------");
  check("today is what you land on", showing("today") && !showing("closet") && !showing("settings"));
  ev(`document.querySelector('.tabs button[data-view="closet"]').click()`);
  check("the closet tab opens the closet", showing("closet") && !showing("today"));
  ev(`$("navSettings").click()`);
  check("the gear opens settings", showing("settings") && !showing("closet"));
  check("and marks itself as the current page",
    w.document.getElementById("navSettings").classList.contains("on"));
  ev(`$("navSettings").click()`);
  check("tapping it again goes back to today", showing("today") && !showing("settings"));
  check("the tab bar follows the view",
    w.document.querySelector('.tabs button[data-view="today"]').classList.contains("on"));

  console.log("\n--- 4. Today still says who it is dressing ------------------------");
  // gender/style moved to Settings, so Today must not become an anonymous form.
  ev(`state.gender="woman"; state.style="smart"; renderProfileLine();`);
  const line = w.document.getElementById("profileLine").textContent;
  check("the profile line names both choices", /Woman/.test(line) && /smart/.test(line), line);
  ev(`document.querySelector('.tabs button[data-view="closet"]').click()`);
  ev(`$("profileEdit").click()`);
  check("its 'change' link jumps to settings", showing("settings"), ev("view"));
  ev(`showView("today")`);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
