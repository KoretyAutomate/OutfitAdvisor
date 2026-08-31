/**
 * warmth_scale.test.js — the warmth scale, measured from home (user, 2026-08-30).
 *
 *   "3 should be referred as the annual average temperature of the home location,
 *    5 the highest, and low the lowest. We should always take the mid point of the
 *    Monthly average range."
 *
 * Warmth 1-5 was absolute: the edit sheet said "1 cool → 5 warm" and nothing said
 * cool for WHERE, while the outer-layer guard fired at a fixed 5/12/18C. The same
 * jumper was a 4 in Singapore and a 4 in Oslo.
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites —
 * no copy of the arithmetic that could drift from the shipped code.
 *
 * Three things a wrong implementation gets wrong quietly:
 *   - the DIRECTION. 5 must stay the wool coat. Inverted, the app recommends a
 *     parka in July and every number in the closet silently changes meaning.
 *   - the FALLBACK. No home, a failed fetch, a cache from a home they have left:
 *     each must land on the absolute table, never on a wrong scale and never on an
 *     exception.
 *   - the TWIN. server/picks.py Climate is the same arithmetic; if the two drift,
 *     the classifier writes a number on one scale and the guard reads it on another.
 *
 * Run: npm test   (or: node tests/warmth_scale.test.js)
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
const SCALE = path.join(__dirname, "..", "..", "server", "scale.py");

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

const HOME = { label: "Princeton", postal: "08540", lat: 40.3, lon: -74.6 };
const COLD = 0.4, AVG = 12.6, HOT = 24.3;
const CACHE = { lat: HOME.lat, lon: HOME.lon, cold: COLD, avg: AVG, hot: HOT, months: [], at: Date.now() };

(async () => {
  const w = page();
  const ev = (c) => w.eval(c);
  await ev("appReady");

  console.log("\n--- 1. the anchors, and only when they are this home's ------------");
  ev(`home=${JSON.stringify(HOME)}; climate=${JSON.stringify(CACHE)};`);
  check("the scale is the three anchors", JSON.stringify(ev("climateAnchors()")) ===
    JSON.stringify({ cold: COLD, avg: AVG, hot: HOT }), ev("JSON.stringify(climateAnchors())"));

  /* A cache left over from a previous home would scale the whole wardrobe to a city
     the wearer has moved away from — silently, and for ever. */
  ev(`home={...home, lat:1.35, lon:103.8};`);
  check("a cache measured at another home is not used",
    ev("climateAnchors()") === null, ev("JSON.stringify(climateAnchors())"));
  ev(`home=${JSON.stringify(HOME)};`);
  check("and is used again when the home comes back", ev("climateAnchors()") !== null);

  ev(`home=null;`);
  check("no home means no scale — there is nowhere to measure from",
    ev("climateAnchors()") === null);
  ev(`home=${JSON.stringify(HOME)};`);

  /* The same refusals picks.Climate.of makes. A degenerate scale would divide by
     zero or grade backwards, and either is worse than the table it replaces. */
  for (const [name, c] of [
    ["a flat year", { ...CACHE, cold: 9, avg: 9, hot: 9 }],
    ["the ends the wrong way round", { ...CACHE, cold: 24, avg: 12, hot: 0 }],
    ["an average outside its own extremes", { ...CACHE, cold: 12, avg: 0, hot: 24 }],
    ["a missing anchor", { ...CACHE, avg: null }],
    ["a non-number", { ...CACHE, hot: "warm" }],
  ]) {
    ev(`climate=${JSON.stringify(c)};`);
    check(`${name} is refused, not used`, ev("climateAnchors()") === null,
      ev("JSON.stringify(climateAnchors())"));
  }
  ev(`climate=${JSON.stringify(CACHE)};`);

  console.log("\n--- 2. what each number answers to --------------------------------");
  const near = (a, b) => Math.abs(a - b) < 1e-9;   // unrounded: see warmthTemp
  check("5 is the coldest month", near(ev("warmthTemp(5)"), COLD), ev("warmthTemp(5)"));
  check("3 is the annual average", near(ev("warmthTemp(3)"), AVG), ev("warmthTemp(3)"));
  check("1 is the warmest month", near(ev("warmthTemp(1)"), HOT), ev("warmthTemp(1)"));
  check("4 sits between 5 and 3", near(ev("warmthTemp(4)"), (COLD + AVG) / 2), ev("warmthTemp(4)"));
  check("2 sits between 3 and 1", near(ev("warmthTemp(2)"), (AVG + HOT) / 2), ev("warmthTemp(2)"));
  ev(`climate=null;`);
  check("and with no scale there is no temperature to show", ev("warmthTemp(3)") === null);
  ev(`climate=${JSON.stringify(CACHE)};`);

  console.log("\n--- 3. the guard reads the scale ---------------------------------");
  /* Called the way callers call it: with the scale the GARMENT was numbered on.
     Defaulting the second argument to the current home's anchors is exactly what
     would re-read an old number on a ruler nothing measured it with. */
  const need = (t) => ev(`minOuterWarmth(${t}, climateAnchors())`);
  check("the coldest month asks for the warmest thing they own", need(COLD) === 5);
  check("the annual average asks for a 3", need(AVG) === 3);
  check("the warmest month asks for a 1", need(HOT) === 1);
  const ws = [];
  for (let t = -10; t < 40; t++) ws.push(need(t));
  check("never warmer clothes for a warmer day",
    ws.every((v, i) => i === 0 || v <= ws[i - 1]), ws.join(","));
  check("and never off the scale", ws.every(v => v >= 1 && v <= 5), ws.join(","));

  /* Round trip: the temperature a number answers to asks for that number back. */
  check("the scale reads the same way in both directions",
    [1, 2, 3, 4, 5].every(n => need(ev(`warmthTemp(${n})`)) === n),
    [1, 2, 3, 4, 5].map(n => need(ev(`warmthTemp(${n})`))));

  /* The fallback is what everybody had before today, and is pinned by value: a
     silent drift here re-grades every closet that has no home area. */
  ev(`climate=null;`);
  check("no scale falls back to the absolute table",
    [0, 4.9, 5, 11.9, 12, 17.9, 18, 30].map(t => ev(`minOuterWarmth(${t})`)).join() ===
      "4,4,3,3,2,2,1,1",
    [0, 4.9, 5, 11.9, 12, 17.9, 18, 30].map(t => ev(`minOuterWarmth(${t})`)));
  check("and the table itself is the twin the server pins",
    JSON.stringify(ev("OUTER_MIN_WARMTH")) === "[[5,4],[12,3],[18,2]]",
    ev("JSON.stringify(OUTER_MIN_WARMTH)"));
  ev(`climate=${JSON.stringify(CACHE)};`);

  console.log("\n--- 4. the twin: server/picks.py Climate --------------------------");
  /* Read out of the Python, not re-typed here. Two implementations of one scale is
     exactly the drift this project has paid for before. */
  const py = fs.readFileSync(SCALE, "utf8");
  check("the server anchors 5/3/1 the same way",
    /WARMTH_COLD, WARMTH_AVG, WARMTH_HOT = 5, 3, 1/.test(py));
  check("and still carries the same absolute fallback",
    /ABSOLUTE_TABLE = \(\(5, 4\), \(12, 3\), \(18, 2\)\)/.test(py));
  /* Python breaks a .5 tie to even and JS takes it upwards, so the server rounds
     half-up explicitly. Without it the two disagree at every threshold they land
     on. Raised by the pre-push reviewer, 2026-08-31. */
  check("and rounds a half step the way this side does",
    /def _half_up/.test(py) && /math\.floor\(x \+ 0\.5\)/.test(py));
  const halves = [[7.5, 4], [12.5, 3]];
  const flat = "{cold:0,avg:10,hot:20}";
  check("a half step lands on the same side as the server",
    halves.every(([t, want]) => ev(`minOuterWarmth(${t}, ${flat})`) === want),
    halves.map(([t]) => ev(`minOuterWarmth(${t}, ${flat})`)));
  ev(`climate=${JSON.stringify(CACHE)};`);

  console.log("\n--- 5. the picker says it in degrees ------------------------------");
  const TEE = { id: "itm-tee-0001", label: "white tee", category: "base", group: "tops",
    type: "t_shirt", roles: ["base"], colors: [], warmth: 1, formality: ["casual"],
    waterproof: false, count: 1 };
  // Graded on the home scale, which is what everything classified from now on is.
  // The garment that has NOT been is section 8's subject.
  ev(`closet=[${JSON.stringify({ ...TEE, warmthScale: "home", warmthAnchors: [COLD, AVG, HOT] })}];`);
  await ev(`openSheet(closet[0],{isNew:false})`);
  const caps = () => [...w.document.querySelectorAll("#shWarm .wt")].map(e => e.textContent);
  check("every number is captioned with the day it is for",
    caps().join("|") === "24°|18°|13°|7°|0°", caps());
  /* The three ANCHORS are the numbers both languages print — the classify prompt
     states cold/avg/hot in degrees, and these captions must not disagree with it.
     4 and 2 are display-only here (the server never prints them), which is just as
     well: 6.5 rounds to 7 in JS and to 6 in Python, and chasing that tie would be
     chasing a number nobody can see twice. */
  check("and the anchors read as the server states them in the prompt",
    caps()[0] === "24°" && caps()[2] === "13°" && caps()[4] === "0°", caps());
  check("and the hint says the captions are about home",
    /at home/.test(w.document.getElementById("shWarmHint").textContent),
    w.document.getElementById("shWarmHint").textContent);

  ev(`climate=null; paintSheetSegs();`);
  check("with no scale the captions go, rather than showing a made-up degree",
    caps().every(c => c === ""), caps());
  check("and the hint falls back to the words it always had",
    /1 cool/.test(w.document.getElementById("shWarmHint").textContent),
    w.document.getElementById("shWarmHint").textContent);
  ev(`climate=${JSON.stringify(CACHE)}; paintSheetSegs();`);
  check("the number picked is still the one shown as chosen",
    w.document.querySelector('#shWarm button[data-w="1"]').classList.contains("on"));

  console.log("\n--- 6. the scale travels with the GARMENT, not the request --------");
  /* What has to be known at 06:45 is what each NUMBER meant when it was written,
     and that does not change when the wearer moves house. So the anchors ride on
     each garment and the request carries no scale at all. */
  ev(`__sent=null; fetch=async(u,o)=>{ __sent={url:u,body:JSON.parse(o.body)};
      return {ok:true,json:async()=>({weather:{lo:1,hi:6,morning:2,date:"2026-08-31"},
        outfit:{base:"tee"},outfit_text:"x",source:"llm"})}; };`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("the request itself states no scale",
    !("climate" in ev("__sent.body")), Object.keys(ev("__sent.body")));
  check("and the garment states its own",
    ev(`__sent.body.closet[0].warmthScale`) === "home" &&
    (ev(`__sent.body.closet[0].warmthAnchors`) || []).join() === [COLD, AVG, HOT].join(),
    ev(`JSON.stringify(__sent.body.closet[0])`));

  ev(`__sent=null; fetch=async(u,o)=>{ __sent={url:u,body:JSON.parse(o.body)};
      return {ok:true,json:async()=>({label:"x",category:"base"})}; };`);
  await ev(`classifyPhoto("${"a".repeat(120)}")`);
  check("/classify still states it — that call is GRADING against it",
    ev("__sent.body.climate").cold === COLD, ev("JSON.stringify(__sent.body.climate)"));

  await ev(`savePushPayload()`);
  const payload = JSON.parse(w.localStorage.getItem("oa.pushPayload") || "{}");
  check("the morning push's wardrobe carries each garment's year",
    (payload.closet[0].warmthAnchors || []).join() === [COLD, AVG, HOT].join(), payload.closet[0]);

  /* A garment graded on the old absolute scale says so, and carries no year. */
  ev(`closet=[${JSON.stringify(TEE)}]; __sent=null;
      fetch=async(u,o)=>{ __sent={url:u,body:JSON.parse(o.body)};
        return {ok:true,json:async()=>({weather:{lo:1,hi:6,morning:2,date:"2026-08-31"},
          outfit:{base:"tee"},outfit_text:"x",source:"llm"})}; };`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("an ungraded garment travels as absolute, with no year",
    ev(`__sent.body.closet[0].warmthScale`) === "absolute" &&
    ev(`__sent.body.closet[0].warmthAnchors`) === null,
    ev(`JSON.stringify(__sent.body.closet[0])`));
  ev(`closet=[${JSON.stringify({ ...TEE, warmthScale: "home", warmthAnchors: [COLD, AVG, HOT] })}];`);

  console.log("\n--- 7. fetching it, and refusing to store a bad one ---------------");
  const wB = page();
  await wB.eval("appReady");
  wB.eval(`home=${JSON.stringify(HOME)}; climate=null;
    fetch=async()=>({ok:true,json:async()=>({months:[],cold:${COLD},avg:${AVG},hot:${HOT},years:10})});`);
  await wB.eval(`refreshClimate()`);
  check("a good answer is kept, keyed to the home it was measured at",
    wB.eval(`climate.lat`) === HOME.lat && wB.eval(`climateAnchors()`) !== null,
    wB.eval(`JSON.stringify(climate)`));
  check("and written down, so it is not refetched every launch",
    JSON.parse(wB.localStorage.getItem("oa.climate") || "null").avg === AVG,
    wB.localStorage.getItem("oa.climate"));
  check("the home card says what the scale is",
    /warmth scale/.test(wB.document.getElementById("climateLine").textContent) &&
    wB.document.getElementById("climateLine").style.display !== "none",
    wB.document.getElementById("climateLine").textContent);

  /* A server that answers something unusable must leave the absolute scale in
     place, not store a scale that grades backwards. */
  const wC = page();
  await wC.eval("appReady");
  wC.eval(`home=${JSON.stringify(HOME)}; climate=null;
    fetch=async()=>({ok:true,json:async()=>({months:[],cold:30,avg:12,hot:0,years:10})});`);
  await wC.eval(`refreshClimate()`);
  check("an unusable answer is not stored",
    wC.eval(`climate`) === null && wC.eval(`climateAnchors()`) === null,
    wC.eval(`JSON.stringify(climate)`));

  /* And an unreachable one costs nothing at all. */
  const wD = page();
  await wD.eval("appReady");
  wD.eval(`home=${JSON.stringify(HOME)}; climate=null;
    fetch=async()=>{ throw new Error("down"); };`);
  await wD.eval(`refreshClimate()`);
  check("an unreachable archive is silent and leaves the absolute scale",
    wD.eval(`climate`) === null && wD.eval(`minOuterWarmth(2)`) === 4,
    wD.eval(`minOuterWarmth(2)`));

  /* Once measured, never refetched — this is the most expensive call the server
     makes, and the answer moves on the scale of decades. */
  const wE = page();
  await wE.eval("appReady");
  wE.eval(`home=${JSON.stringify(HOME)}; climate=${JSON.stringify(CACHE)};
    __calls=0; fetch=async()=>{ __calls++; return {ok:false,status:500}; };`);
  await wE.eval(`refreshClimate()`);
  check("a scale already measured for this home is not fetched again",
    wE.eval(`__calls`) === 0, wE.eval(`__calls`));
  wE.eval(`home={...home, lat:1.35, lon:103.8};`);
  await wE.eval(`refreshClimate()`);
  check("but moving house measures again", wE.eval(`__calls`) === 1, wE.eval(`__calls`));

  /* A home changed WHILE the archive call is in flight. Stamping the answer with
     whatever `home` says on the way out filed the first home's climate under the
     second's coordinates — accepted by climateAnchors(), and climateBusy then
     stopped anything measuring the home they had actually moved to. Raised by the
     pre-push reviewer, 2026-08-31. */
  const wM = page();
  await wM.eval("appReady");
  wM.eval(`home=${JSON.stringify(HOME)}; climate=null; __calls=[];
    fetch=async(u,o)=>{ const b=JSON.parse(o.body); __calls.push(b.lat);
      // the wearer moves house while this one is in flight
      if(__calls.length===1) home={...home, lat:1.35, lon:103.8};
      return {ok:true,json:async()=>(b.lat===1.35
        ? {months:[],cold:26.3,avg:27.1,hot:27.7,years:10}
        : {months:[],cold:${COLD},avg:${AVG},hot:${HOT},years:10})}; };`);
  await wM.eval(`refreshClimate()`);
  await new Promise(r => setTimeout(r, 30));
  check("an answer about the home they left is not stamped with the new one",
    wM.eval(`climate===null||climate.lat===1.35`), wM.eval(`JSON.stringify(climate)`));
  check("and the home they moved TO is measured instead",
    wM.eval(`__calls`).includes(1.35) && wM.eval(`climateAnchors()`) !== null,
    { calls: wM.eval(`__calls`), got: wM.eval(`JSON.stringify(climate)`) });
  check("with that home's own anchors, not the old ones",
    wM.eval(`climateAnchors()`).cold === 26.3, wM.eval(`JSON.stringify(climateAnchors())`));

  /* Moving house does not re-grade a wardrobe. The push payload states no scale of
     its own — there is none to go stale in it — and each garment keeps the year its
     number was actually written against, which is the whole reason the anchors sit
     on the garment rather than on the request. */
  const wN = page();
  await wN.eval("appReady");
  wN.eval(`home=${JSON.stringify(HOME)}; climate=${JSON.stringify(CACHE)};
    closet=[${JSON.stringify({ ...TEE, warmthScale: "home", warmthAnchors: [COLD, AVG, HOT] })}];`);
  await wN.eval(`savePushPayload()`);
  check("the payload states no scale of its own",
    !("climate" in JSON.parse(wN.localStorage.getItem("oa.pushPayload"))),
    Object.keys(JSON.parse(wN.localStorage.getItem("oa.pushPayload"))));
  wN.eval(`fetch=async()=>{ throw new Error("down"); };`);
  wN.eval(`home={label:"Singapore",postal:"",lat:1.35,lon:103.8};`);
  await wN.eval(`saveHome()`);
  await wN.eval(`refreshClimate()`);        // and it fails, which changes nothing
  await wN.eval(`savePushPayload()`);
  check("and the wardrobe keeps the year it was graded against",
    (JSON.parse(wN.localStorage.getItem("oa.pushPayload")).closet[0]
      .warmthAnchors || []).join() === [COLD, AVG, HOT].join(),
    wN.localStorage.getItem("oa.pushPayload"));
  check("while the app itself falls back, having no scale for the new home",
    wN.eval(`climateAnchors()`) === null);

  console.log("\n--- 8. an old number is not re-read on the new ruler --------------");
  /* The absolute table's implicit warmth 3 is about 8C; a real annual average is
     nearer 13. Reading an old number with the new scale demotes every garment in
     the closet at once, without anybody touching it. Each garment is judged on the
     scale it was numbered on, and migrates when it is re-graded. Raised by the
     pre-push reviewer, 2026-08-31. */
  const wS = page();
  await wS.eval("appReady");
  wS.eval(`home=${JSON.stringify(HOME)}; climate=${JSON.stringify(CACHE)};
    closet=[${JSON.stringify({ ...TEE, warmth: 3 })}];`);
  check("a closet saved before the stamp existed reads as the old scale",
    wS.eval(`closetPayload()[0].warmthScale`) === "absolute",
    wS.eval(`JSON.stringify(closetPayload()[0])`));

  await wS.eval(`openSheet(closet[0],{isNew:false})`);
  check("and the sheet says so, with the way to fix it",
    /old scale/.test(wS.document.getElementById("shWarmHint").textContent),
    wS.document.getElementById("shWarmHint").textContent);
  wS.eval(`document.querySelector('#shWarm button[data-w="4"]').click()`);
  check("tapping a number re-grades it — the captions are what they read",
    wS.eval(`sheet.item.warmthScale`) === "home" && wS.eval(`sheet.item.warmth`) === 4,
    wS.eval(`JSON.stringify({s:sheet.item.warmthScale,w:sheet.item.warmth})`));
  check("and the sheet stops warning once it is graded",
    /at home/.test(wS.document.getElementById("shWarmHint").textContent),
    wS.document.getElementById("shWarmHint").textContent);
  await wS.eval(`document.getElementById("shSave").onclick()`);
  check("saving carries the re-grade into the closet",
    wS.eval(`closet[0].warmthScale`) === "home" && wS.eval(`closet[0].warmth`) === 4,
    wS.eval(`JSON.stringify(closet[0])`));

  /* With no scale to grade against, a tap must not claim one — and must not leave
     an OLDER claim standing either. The buttons carry no degrees then, so the number
     chosen is an absolute one; keeping a previous home's stamp would have it judged
     against a year it was never chosen in, which is exactly the state right after a
     move while /climate is still loading or has failed. Raised by the pre-push
     reviewer, 2026-08-31. */
  const wT = page();
  await wT.eval("appReady");
  wT.eval(`home=null; climate=null; closet=[${JSON.stringify(TEE)}];`);
  await wT.eval(`openSheet(closet[0],{isNew:false})`);
  wT.eval(`document.querySelector('#shWarm button[data-w="4"]').click()`);
  check("with no home, a tap sets the number and claims no scale",
    wT.eval(`sheet.item.warmthScale`) !== "home" && wT.eval(`sheet.item.warmth`) === 4,
    wT.eval(`String(sheet.item.warmthScale)`));

  wT.eval(`closet=[${JSON.stringify({ ...TEE, warmthScale: "home", warmthAnchors: [COLD, AVG, HOT] })}];
           home=null; climate=null;`);
  await wT.eval(`openSheet(closet[0],{isNew:false})`);
  wT.eval(`document.querySelector('#shWarm button[data-w="2"]').click()`);
  check("and a stale claim from a previous home is dropped, not inherited",
    wT.eval(`sheet.item.warmthScale`) === "absolute" &&
    wT.eval(`sheet.item.warmthAnchors`) === null,
    wT.eval(`JSON.stringify({s:sheet.item.warmthScale,a:sheet.item.warmthAnchors})`));

  /* The gap check asks the same question the server's guard does, of the same
     garment, in the same units. Asking only for the NUMBER here — while the server
     asked for the scale — is how the evidence and the advice come to disagree about
     one wardrobe. */
  wS.eval(`climate=${JSON.stringify(CACHE)};`);
  check("an old-scale garment is judged by the old table on this side too",
    wS.eval(`warmEnough({warmth:4},2)`) === true &&
    wS.eval(`warmEnough({warmth:4,warmthScale:"home",warmthAnchors:[${COLD},${AVG},${HOT}]},2)`) === false,
    [wS.eval(`warmEnough({warmth:4},2)`),
     wS.eval(`warmEnough({warmth:4,warmthScale:"home",warmthAnchors:[${COLD},${AVG},${HOT}]},2)`)]);

  /* And the stamp has to reach the server, or it is judged there on the wrong one. */
  wS.eval(`__sent=null; fetch=async(u,o)=>{ __sent={url:u,body:JSON.parse(o.body)};
    return {ok:true,json:async()=>({weather:{lo:1,hi:6,morning:2,date:"2026-08-31"},
      outfit:{base:"tee"},outfit_text:"x",source:"llm"})}; };`);
  await wS.eval(`getAdvice(40.3,-74.6)`);
  check("/advice carries each garment's scale, not only its number",
    wS.eval(`__sent.body.closet[0].warmthScale`) === "home",
    wS.eval(`JSON.stringify(__sent.body.closet[0])`));
  await wS.eval(`savePushPayload()`);
  check("and so does the morning push's wardrobe",
    JSON.parse(wS.localStorage.getItem("oa.pushPayload")).closet[0].warmthScale === "home",
    wS.localStorage.getItem("oa.pushPayload"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
