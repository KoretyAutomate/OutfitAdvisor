/**
 * tabs.test.js — the app is three sheets, not one scroll (2026-08-20).
 *
 * The user asked for the page to be split into location & style + advice, closet,
 * and calendar, "shown like three different tabs like how excel shows different
 * sheets". Splitting a single page is the kind of change that looks right in a
 * screenshot and is wrong in the DOM: a control left in the wrong section, or two
 * sections visible at once, or a modal that ended up inside a hidden pane and can
 * never be opened again.
 *
 * So this checks WHERE each control lives and what is visible, not how it looks.
 *
 * Run: npm test   (or: node tests/tabs.test.js — jsdom is a devDependency since 2026-08-20)
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
const doc = w.document;
const ev = (c) => w.eval(c);
const drain = () => new Promise(r => setTimeout(r, 0));

/** Which sheet is this control on? null means it is on none of them. */
const sheetOf = (id) => {
  const el = doc.getElementById(id);
  if (!el) return "MISSING";
  const pane = el.closest("section.pane");
  return pane ? pane.id.replace(/^pane-/, "") : null;
};
const visible = () => [...doc.querySelectorAll("section.pane")]
  .filter(p => p.classList.contains("on")).map(p => p.id.replace(/^pane-/, ""));

(async () => {
  // Wait for the page to finish initialising. appReady is the real signal;
  // polling for a field load() happens to set early is a guess about one.
  await ev("appReady");

  console.log("\n--- 1. three sheets, and the strip names the same three -----------");
  const panes = [...doc.querySelectorAll("section.pane")].map(p => p.id);
  check("the page is built from exactly three panes",
    JSON.stringify(panes) === '["pane-advice","pane-closet","pane-calendar"]', panes);
  const tabs = [...doc.getElementById("tabBar").children].map(b => b.dataset.tab);
  check("and the tab strip offers exactly those three",
    JSON.stringify(tabs) === '["advice","closet","calendar"]', tabs);
  check("the code's list agrees with the markup",
    JSON.stringify(ev("TABS")) === JSON.stringify(tabs), ev("TABS"));

  console.log("\n--- 2. every control is on the sheet the user was promised --------");
  // "location & style + advice"
  for (const id of ["city", "geoBtn", "goBtn", "genderSeg", "styleSeg", "err",
                    "wxCard", "outfitCard", "aiText", "fbRow", "dShare"])
    check(`${id} is on the location & advice sheet`, sheetOf(id) === "advice", sheetOf(id));
  // "closet"
  for (const id of ["closetGrid", "addCamBtn", "addGalBtn", "laundryBtn", "clErr"])
    check(`${id} is on the closet sheet`, sheetOf(id) === "closet", sheetOf(id));
  // "calendar"
  for (const id of ["homeLine", "homeBtn", "calSelLine", "calPickBtn", "calBtn",
                    "tripList", "candList", "tripErr"])
    check(`${id} is on the calendar sheet`, sheetOf(id) === "calendar", sheetOf(id));

  console.log("\n--- 3. what must NOT be trapped on one sheet ----------------------");
  check("the update banner is on no sheet — a stale build must say so on any page",
    sheetOf("updCard") === null, sheetOf("updCard"));
  check("the settings gear is reachable from every page", sheetOf("gearBtn") === null);
  for (const id of ["sheetWrap", "tripWrap", "setWrap", "calWrap", "packWrap"])
    check(`the ${id} modal is outside the panes, so switching cannot bury it`,
      sheetOf(id) === null, sheetOf(id));

  console.log("\n--- 4. exactly one sheet at a time --------------------------------");
  ev(`showTab("advice")`);
  check("one sheet is showing, and it is the one asked for",
    JSON.stringify(visible()) === '["advice"]', visible());
  ev(`showTab("closet")`);
  check("switching hides the previous sheet rather than stacking",
    JSON.stringify(visible()) === '["closet"]', visible());
  check("and the tab strip marks the sheet you are on",
    [...doc.getElementById("tabBar").children]
      .filter(b => b.classList.contains("on")).map(b => b.dataset.tab).join() === "closet");

  ev(`showTab("calendar")`);
  check("the third sheet works too", JSON.stringify(visible()) === '["calendar"]', visible());

  console.log("\n--- 5. it remembers which sheet you were on -----------------------");
  await drain();
  check("choosing a sheet is written down",
    w.localStorage.getItem("oa.tab") === "calendar", w.localStorage.getItem("oa.tab"));
  // Restoring is not a new choice — it must not overwrite anything.
  w.localStorage.setItem("oa.tab", "closet");
  ev(`showTab("advice", false)`);
  await drain();
  check("restoring a remembered sheet does not overwrite the memory",
    w.localStorage.getItem("oa.tab") === "closet", w.localStorage.getItem("oa.tab"));

  ev(`showTab("nonsense")`);
  check("a sheet name we no longer have falls back to the first, not to a blank page",
    JSON.stringify(visible()) === '["advice"]', visible());

  console.log("\n--- 6. the strip is wired ----------------------------------------");
  doc.querySelector('#tabBar button[data-tab="closet"]').click();
  check("tapping a tab switches to it", JSON.stringify(visible()) === '["closet"]', visible());

  console.log("\n--- 7. the strip is at the TOP (user, 2026-08-23) ---------------");
  /* Position is a REQUEST, not a detail: the bar was built along the bottom and
     the user asked for it at the top. DOM order is what is asserted, because that
     is what survives a CSS refactor — a rule that stops applying leaves the bar
     wherever the markup put it. */
  const bar = doc.getElementById("tabBar");
  const firstPane = doc.querySelector("section.pane");
  check("the tab bar comes BEFORE the panes in document order",
    !!(bar.compareDocumentPosition(firstPane) & 4), "bar is after the panes");
  check("it sits under the header, not above it",
    !!(doc.querySelector("header").compareDocumentPosition(bar) & 4),
    "bar is above the header");
  check("it is inside the page wrapper, so it lines up with the cards",
    bar.closest(".wrap") !== null);
  check("and it is still the only tab bar", doc.querySelectorAll("#tabBar").length === 1);

  /* A sticky bar pinned at viewport 0 slides under the status bar or the camera
     cutout on an edge-to-edge phone once the header scrolls away, and stops being
     tappable. Raised by the pre-push reviewer, 2026-08-23. jsdom does not compute
     env(), so the RULE is asserted rather than the layout. */
  const css = fs.readFileSync(HTML, "utf8");
  const rule = css.slice(css.indexOf(".sheetTabs{"));
  const decl = rule.slice(0, rule.indexOf("}"));
  check("the sticky bar is offset by the safe-area inset, not pinned at 0",
    /top:\s*env\(safe-area-inset-top/.test(decl), decl.slice(0, 120));
  check("and it is sticky, so it survives the header scrolling away",
    /position:\s*sticky/.test(decl), decl.slice(0, 120));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
