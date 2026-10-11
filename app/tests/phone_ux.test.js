/**
 * phone_ux.test.js — the phone-side fixes of 2026-10-11.
 *
 * Loads the REAL app/www/index.html in jsdom (and reads the real Kotlin sources
 * where the behaviour lives natively — no Kotlin toolchain on this box), same
 * discipline as the other suites.
 *
 * Run: npm test   (or: node tests/phone_ux.test.js)
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
const KT = name => fs.readFileSync(path.join(__dirname, "..", "android", "app", "src", "main",
  "java", "com", "korety", "outfitadvisor", name), "utf8");
const SRC = fs.readFileSync(HTML, "utf8");

let passed = 0, failed = 0;
const check = (name, cond, detail = "") => {
  if (cond) { passed++; console.log(`[PASS] ${name}`); }
  else { failed++; console.log(`[FAIL] ${name}  ${JSON.stringify(detail)}`); }
};
const page = () => new JSDOM(SRC, {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
}).window;
const drain = () => new Promise(r => setTimeout(r, 0));

(async () => {
  console.log("\n--- trips privacy wording is truthful ----------------------------");
  {
    const w = page();
    // Two elements share id="tripNote" (the advice card has one too); this is the Trips tab one.
    const note = [...w.document.querySelectorAll("#tripNote")].map(e => e.textContent).join(" ").replace(/\s+/g, " ");
    const body = (SRC.match(/body:JSON\.stringify\(\{title:c\.title,location:c\.hint/) || [])[0];
    check("triageCandidate does send the title and the location text", !!body);
    check("so the note no longer claims they are never sent",
      !/never the event's title/.test(note) &&
      !/only the dates and the city's coordinates are ever sent/.test(note), note);
    check("it says title and location text go to the user's own server",
      /title, location text/.test(note) && /your own advisor server/.test(note), note);
    check("and that the server does not store them", /does not store them/.test(note), note);
  }

  console.log("\n--- the push sends an empty closet only when it is complete ------");
  {
    const kt = KT("AdviceWorker.kt");
    const fn = kt.slice(kt.indexOf("private fun attachWardrobe"));
    const body = fn.slice(0, fn.indexOf("\n    }\n"));
    const empty = body.indexOf("if (closet.length() == 0) {");
    const firstPut = body.indexOf('body.put("closet", closet)');
    check("the app sends [] only under a complete closet (the rule being mirrored)",
      /if\(cl\.length\|\|closetComplete\) body\.closet=cl;/.test(SRC));
    check("the worker reads the tickbox into a value it can test later",
      /val complete = prefs\.getString\(KEY_CLOSET_COMPLETE, "0"\) == "1"/.test(body));
    check("no closet is put before the empty check", empty > 0 && firstPut > empty, { empty, firstPut });
    const block = body.slice(empty, body.indexOf("}", empty));
    check("an empty closet goes only when complete, then stops",
      /if \(complete\) body\.put\("closet", closet\)\s*\n\s*return/.test(block), block);
    check("a non-empty closet is still sent",
      /\}\s*\n\s*body\.put\("closet", closet\)/.test(body.slice(empty)));
  }

  console.log("\n--- one profile settings place -----------------------------------");
  {
    const w = page();
    const d = w.document, ev = c => w.eval(c);
    await ev("appReady");
    const set = d.getElementById("setWrap");
    const head = set.querySelector("h3:nth-of-type(2)");
    check("the Settings sheet opens on a Profile section", head && head.id === "profileHead",
      head && head.textContent);
    for (const id of ["genderSeg", "styleSeg", "closetDone"]) {
      check(`${id} is in Settings → Profile`, !!d.querySelector(`#profileBox #${id}`));
      check(`and only there (one ${id} in the page)`, d.querySelectorAll(`#${id}`).length === 1);
    }
    check("none of them is left on the Advice card or the Closet tab",
      !d.querySelector("#pane-advice #genderSeg, #pane-advice #styleSeg, #pane-closet #closetDone"));
    check("trip settings stay on the Trips tab",
      ["homeBtn", "calPickBtn"].every(id => d.querySelector(`#pane-calendar #${id}`)));

    // Behaviour unchanged: same handlers, same state, same keys.
    d.querySelector('#genderSeg button[data-g="woman"]').click();
    await drain(); await drain();
    check("Gender still sets state and oa.gender", ev("state.gender") === "woman" &&
      w.localStorage.getItem("oa.gender") === "woman", ev("state.gender"));
    check("and paints the segment", d.querySelector('#genderSeg button[data-g="woman"]').classList.contains("on"));
    d.querySelector('#styleSeg button[data-s="smart"]').click();
    await drain(); await drain();
    check("Style still sets state and oa.style", ev("state.style") === "smart" &&
      w.localStorage.getItem("oa.style") === "smart", ev("state.style"));
    const cb = d.getElementById("closetDone");
    cb.checked = true; cb.dispatchEvent(new w.Event("change"));
    await drain(); await drain();
    check("My closet is complete still sets closetComplete and oa.closetComplete",
      ev("closetComplete") === true && w.localStorage.getItem("oa.closetComplete") === "1");
    check("the shopping note sends people to Settings for it",
      /in Settings/.test(SRC.match(/Tick \\u201cMy closet is complete\\u201d[^`"]*/)[0]));
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
