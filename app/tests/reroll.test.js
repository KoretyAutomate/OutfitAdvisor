/**
 * reroll.test.js — asking again has to give you something else (user, 2026-09-03).
 *
 *   "the recommendation doesn't change when I want to get a new advice"
 *
 * And it did not. Four identical /advice calls to the live server returned the same
 * top and the same trousers every time: the request was byte-identical, so nothing
 * in it distinguished "tell me what to wear" from "tell me something else".
 *
 * The server keeps nothing between requests — that is the privacy property this app
 * is built on — so this phone is the only party that can say what it has already
 * been shown. These tests cover that half: that `shown` is sent when there IS an
 * outfit on screen, is not sent when there is not, names only closet picks, and
 * that the button says what a second tap does.
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * Run: npm test   (or: node tests/reroll.test.js)
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

const page = () => {
  const dom = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  });
  return dom.window;
};

const WX = {lo:20, hi:29, desc:"Clear", rain:0, wind:2, code:0, emoji:"☀️",
  swing:9, feelsLo:19, feelsHi:30, morning:21, midday:28, evening:24,
  isRain:false, isSnow:false, date:new Date().toISOString().slice(0,10)};

const CLOSET = [
  {id:"itm-tee-0001", label:"navy tee", category:"base", group:"tops",
   type:"t_shirt", roles:["base"], colors:["navy"], warmth:2,
   formality:["casual"], waterproof:false, count:3, dirty:0},
  {id:"itm-tee-0002", label:"white tee", category:"base", group:"tops",
   type:"t_shirt", roles:["base"], colors:["white"], warmth:2,
   formality:["casual"], waterproof:false, count:3, dirty:0},
  {id:"itm-btm-0001", label:"chinos", category:"bottoms", group:"bottoms",
   type:"chinos", roles:["bottoms"], colors:["navy"], warmth:3,
   formality:["casual"], waterproof:false, count:2, dirty:0},
];

const OUTFIT = {inner:"", base:"navy tee", mid:"", outer:"", bottoms:"chinos",
  footwear:"sneakers", accessories:"", tip:"nice day"};
const PICKS = {inner:null, base:"itm-tee-0001", mid:null, outer:null,
  bottoms:"itm-btm-0001", footwear:null, accessories:null};

/* A closet answer already on the screen. */
const FROM_CLOSET = {weather:WX, outfit:OUTFIT, text:"wear the navy tee",
  source:"llm", picks:PICKS, closetUsed:true};
/* Generic advice: no wardrobe was used, so there are no ids to differ from. */
const GENERIC = {weather:WX, outfit:OUTFIT, text:"wear a tee", source:"llm",
  picks:null, closetUsed:false};

/* Captures the body of the next POST /advice, and answers it. */
function captureAdvice(w, answer) {
  const sent = [];
  w.fetch = async (url, opts) => {
    if (String(url).endsWith("/advice")) {
      sent.push(JSON.parse(opts.body));
      return {ok:true, status:200, json: async () => answer};
    }
    return {ok:true, status:200, json: async () => ({})};
  };
  return sent;
}

(async () => {
  console.log("\n--- 1. what is on the screen ------------------------------------");
  const w = page();
  await w.eval("appReady");
  check("nothing shown yet means nothing to differ from",
    w.eval("shownNow()") === null);

  w.eval(`lastRes=${JSON.stringify(FROM_CLOSET)}`);
  const sn = w.eval("JSON.stringify(shownNow())");
  check("a closet answer names its picks", JSON.parse(sn).base === "itm-tee-0001", sn);
  check("and an empty slot is left out, not sent as null",
    !("inner" in JSON.parse(sn)) && !("footwear" in JSON.parse(sn)), sn);

  w.eval(`lastRes=${JSON.stringify(GENERIC)}`);
  check("generic advice has no ids to name, so nothing is sent",
    w.eval("shownNow()") === null);

  /* The offline recommender dresses from a catalogue. Its outfit is real and its
     picks are null — there is no garment there for the server to avoid. */
  w.eval(`lastRes={...${JSON.stringify(FROM_CLOSET)},source:"offline",picks:null,closetUsed:false}`);
  check("an offline answer is not something the server can differ from",
    w.eval("shownNow()") === null);

  console.log("\n--- 2. the day's FIRST ask carries nothing ----------------------");
  const w2 = page();
  await w2.eval("appReady");
  await w2.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  w2.eval(`state.lat=40.7; state.lon=-74.0; state.city=""`);
  let sent = captureAdvice(w2, {weather:WX, outfit:OUTFIT, outfit_text:"x",
    source:"llm", picks:PICKS, closetUsed:true, missing:[]});
  await w2.eval("run()");
  check("one request went out", sent.length === 1, sent.length);
  check("a wardrobe was sent with it", (sent[0].closet || []).length === 3,
    (sent[0].closet || []).length);
  check("and it does NOT say what was already shown — there was nothing",
    !("shown" in sent[0]), Object.keys(sent[0]));

  console.log("\n--- 3. the SECOND ask says what to move on from -----------------");
  await w2.eval("run()");
  check("a second request went out", sent.length === 2, sent.length);
  check("carrying the outfit the first one produced",
    sent[1].shown && sent[1].shown.base === "itm-tee-0001", sent[1].shown);
  check("the trousers too", sent[1].shown && sent[1].shown.bottoms === "itm-btm-0001",
    sent[1].shown);
  check("an empty slot is not named as something to avoid",
    sent[1].shown && !("outer" in sent[1].shown), sent[1].shown);

  console.log("\n--- 4. only the LAST outfit, never a growing list ---------------");
  /* Accumulating every outfit shown today would narrow a small wardrobe to nothing
     by the third tap. The promise is that the card differs from the card. */
  sent.length = 0;
  w2.fetch = async (url, opts) => {
    if (String(url).endsWith("/advice")) {
      sent.push(JSON.parse(opts.body));
      return {ok:true, status:200, json: async () => ({weather:WX, outfit:OUTFIT,
        outfit_text:"x", source:"llm", closetUsed:true, missing:[],
        picks:{...PICKS, base:"itm-tee-0002"}})};
    }
    return {ok:true, status:200, json: async () => ({})};
  };
  await w2.eval("run()");
  await w2.eval("run()");
  check("the second re-roll avoids what is on screen NOW",
    sent[1].shown.base === "itm-tee-0002", sent[1].shown);
  check("not what was on screen before it",
    Object.keys(sent[1].shown).length === 2, sent[1].shown);

  console.log("\n--- 5. the button says what a second tap does -------------------");
  const w3 = page();
  await w3.eval("appReady");
  check("with nothing answered it offers advice",
    w3.document.getElementById("goBtn").textContent === "Get advice",
    w3.document.getElementById("goBtn").textContent);

  await w3.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  w3.eval(`state.lat=40.7; state.lon=-74.0; state.city=""`);
  captureAdvice(w3, {weather:WX, outfit:OUTFIT, outfit_text:"x", source:"llm",
    picks:PICKS, closetUsed:true, missing:[]});
  await w3.eval("run()");
  check("once it has answered, it offers a different outfit",
    w3.document.getElementById("goBtn").textContent === "Show me something else",
    w3.document.getElementById("goBtn").textContent);
  check("and it is not left spinning or disabled",
    w3.document.getElementById("goBtn").disabled === false);

  /* run() used to restore the caption it captured BEFORE the request, which would
     put "Get advice" back over an outfit the next tap can differ from — hiding the
     feature for the rest of the day. */
  console.log("\n--- 6. restored from this morning's push ------------------------");
  const w4 = page();
  w4.localStorage.setItem("oa.today", JSON.stringify({
    day: new Date().toISOString().slice(0,10), at: Date.now(), how: "push",
    place: "", weather: WX, outfit: OUTFIT, outfit_text: "wear the navy tee",
    source: "llm", picks: PICKS, closetUsed: true, missing: [], planTemp: 24}));
  await w4.eval("appReady");
  check("the push's outfit is something to differ from too",
    w4.eval("JSON.stringify(shownNow())") !== "null",
    w4.eval("JSON.stringify(shownNow())"));
  check("so the button offers it without asking the server first",
    w4.document.getElementById("goBtn").textContent === "Show me something else",
    w4.document.getElementById("goBtn").textContent);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
