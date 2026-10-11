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
const WX = {lo:12, hi:20, desc:"Cloudy", rain:10, wind:3, code:3, emoji:"☁️",
  swing:8, feelsLo:11, feelsHi:19, morning:13, midday:19, evening:15,
  isRain:false, isSnow:false};
const OUTFIT = {inner:"", base:"navy tee", mid:"", outer:"light jacket",
  bottoms:"jeans", footwear:"sneakers", accessories:"", tip:""};

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

  console.log("\n--- one warmth rating a day, shared with the notification --------");
  {
    const w = page();
    const d = w.document, ev = c => w.eval(c), ls = w.localStorage;
    await ev("appReady");
    const tap = async r => { d.querySelector(`#fbRow button[data-r="${r}"]`).click(); await ev("fbChain"); };
    ls.setItem("oa.feedback", "[]"); ls.setItem("oa.tempOffset", "0");
    ev("feedback=[]; tempOffset=0;");
    await tap(2);
    check("a first rating today is recorded", ev("feedback.length") === 1 && ev("tempOffset") === 0.75,
      ev("JSON.stringify(feedback)"));
    // The card is re-rendered (new advice, a restored push): the day is still rated.
    ls.setItem("oa.today", JSON.stringify({day: ev("todayISO()"), at: Date.now(), how: "app",
      weather: WX, outfit: OUTFIT, outfit_text: "x", source: "llm", picks: null, closetUsed: false}));
    await ev("loadToday()");
    check("re-rendering the advice does not clear today's rating",
      d.querySelector('#fbRow button[data-r="2"]').classList.contains("on"));
    await tap(-2);
    check("a second verdict the same day REPLACES the first (one entry)",
      ev("feedback.length") === 1 && ev("feedback[0].rating") === -2, ev("JSON.stringify(feedback)"));
    check("and the offset carries only the final verdict", ev("tempOffset") === -0.75, ev("tempOffset"));

    // The notification rated while the page sat in memory with stale copies.
    ls.setItem("oa.feedback", JSON.stringify([{at: Date.now(), rating: 2}]));
    ls.setItem("oa.tempOffset", "0.75");
    ev("feedback=[]; tempOffset=0;");
    await tap(-1);
    check("a rating after the notification's replaces it, read from disk not memory",
      ev("feedback.length") === 1 && ev("feedback[0].rating") === -1 && ev("tempOffset") === -0.3,
      { fb: ev("JSON.stringify(feedback)"), off: ev("tempOffset") });

    // Yesterday's rating is yesterday's.
    const y = Date.now() - 36 * 3600 * 1000;
    ls.setItem("oa.feedback", JSON.stringify([{at: y, rating: 2}])); ls.setItem("oa.tempOffset", "0.75");
    await tap(-2);
    check("yesterday's rating is kept and today's added", ev("feedback.length") === 2 &&
      ev("tempOffset") === 0, { fb: ev("JSON.stringify(feedback)"), off: ev("tempOffset") });

    // Two quick taps queue rather than race or drop.
    ls.setItem("oa.feedback", "[]"); ls.setItem("oa.tempOffset", "0");
    const b2 = d.querySelector('#fbRow button[data-r="2"]'), b0 = d.querySelector('#fbRow button[data-r="0"]');
    b2.click(); b0.click();
    await ev("fbChain");
    check("two quick taps land as the final verdict only",
      ev("feedback.length") === 1 && ev("feedback[0].rating") === 0 && ev("tempOffset") === 0,
      { fb: ev("JSON.stringify(feedback)"), off: ev("tempOffset") });

    console.log("\n--- back in the foreground, the page re-reads what the native side wrote");
    const today = ev("todayISO()");
    ls.setItem("oa.tempOffset", "-1.5");
    ls.setItem("oa.feedback", JSON.stringify([{at: Date.now(), rating: -2}]));
    ls.setItem("oa.wearlog", JSON.stringify([{itemId: "tee1", wornAt: Date.now()}]));
    ls.setItem("oa.woreToday", JSON.stringify({day: today, map: {base: "tee1"}}));
    ls.setItem("oa.today", JSON.stringify({day: today, at: Date.now() + 5, how: "push",
      weather: WX, outfit: OUTFIT, outfit_text: "from the push", source: "llm",
      picks: {base: "tee1"}, closetUsed: true}));
    d.dispatchEvent(new w.Event("visibilitychange"));
    for (let i = 0; i < 20 && ev("sharedBusy"); i++) await new Promise(r => setTimeout(r, 10));
    await drain();
    check("oa.tempOffset re-read", ev("tempOffset") === -1.5, ev("tempOffset"));
    check("oa.feedback re-read", ev("feedback.length") === 1 && ev("feedback[0].rating") === -2);
    check("oa.wearlog re-read", ev("wearLog.length") === 1 && ev("wearLog[0].itemId") === "tee1",
      ev("JSON.stringify(wearLog)"));
    check("oa.woreToday re-read", ev("JSON.stringify(woreLogged)") === '{"base":"tee1"}',
      ev("JSON.stringify(woreLogged)"));
    check("today's push advice is shown", ev("lastText") === "from the push", ev("lastText"));
    check("and the wear button reports it as logged", ev("wornLogged") === true &&
      /Logged/.test(d.getElementById("dWear").textContent), d.getElementById("dWear").textContent);
  }

  console.log("\n--- FeedbackReceiver.kt mirrors one-rating-a-day ------------------");
  {
    const kt = KT("FeedbackReceiver.kt");
    check("it finds today's entry by local calendar day",
      /dayOf\(e\.optLong\("at", 0L\)\) == today/.test(kt) && /SimpleDateFormat\("yyyy-MM-dd"/.test(kt));
    check("reverts its step before applying the new one (twin of fbRevert)",
      /current = clamp\(round2\(current - RATE \* prev\)\)/.test(kt) &&
      kt.indexOf("current - RATE * prev") < kt.indexOf("current + RATE * delta"));
    check("and drops it, so the day keeps one entry", /log\.remove\(prevIdx\)/.test(kt));
    check("the new entry uses the same clock as the day test", /put\("at", now\)/.test(kt));
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
