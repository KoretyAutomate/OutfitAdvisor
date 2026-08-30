/**
 * today_rules.test.js — two things the user asked for on 2026-08-24.
 *
 *   1. The advice stays for the rest of the day, including the advice the MORNING
 *      PUSH already worked out. It used to vanish when the app was closed, and the
 *      push's answer vanished the moment the app was opened — a second 30-second
 *      wait for something the phone had had since 06:45.
 *   2. Free-text feedback ("white V-neck inner + white T shall be banned") becomes
 *      a rule the SERVER enforces, not prose in a prompt.
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * Run: npm test   (or: node tests/today_rules.test.js)
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
const WORKER = path.join(__dirname, "..", "android", "app", "src", "main", "java",
                         "com", "korety", "outfitadvisor", "AdviceWorker.kt");

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

const WX = {lo:12, hi:20, desc:"Cloudy", rain:10, wind:3, code:3, emoji:"☁️",
  swing:8, feelsLo:11, feelsHi:19, morning:13, midday:19, evening:15,
  isRain:false, isSnow:false, date:new Date().toISOString().slice(0,10)};
const OUTFIT = {inner:"", base:"navy tee", mid:"", outer:"light jacket",
  bottoms:"jeans", footwear:"sneakers", accessories:"", tip:"take a brolly"};
const RES = {weather:WX, outfit:OUTFIT, text:"wear the navy tee", source:"llm",
  picks:null, closetUsed:false};

(async () => {
  const w = page();
  const ev = (c) => w.eval(c);
  await ev("appReady");

  console.log("\n--- 1. today's advice is written down ---------------------------");
  await ev(`saveToday(${JSON.stringify(RES)},"app")`);
  const raw = w.localStorage.getItem("oa.today");
  check("it is stored", !!raw);
  const stored = JSON.parse(raw || "{}");
  check("stamped with the DAY, not an age — yesterday's advice is wrong, not stale",
    stored.day === ev("todayISO()"), stored.day);
  check("the weather is kept", stored.weather && stored.weather.hi === 20);
  check("and the outfit with it", stored.outfit && stored.outfit.base === "navy tee");
  check("no coordinates are stored — the RAM-only rule still holds",
    !("lat" in stored) && !("lon" in stored), Object.keys(stored));

  console.log("\n--- 2. and read back when the app opens -------------------------");
  const w2 = page();
  w2.localStorage.setItem("oa.today", raw);
  await w2.eval("appReady");
  check("the weather card is on screen without asking the server again",
    w2.document.getElementById("wxCard").style.display === "block");
  check("the outfit is rendered too",
    w2.document.getElementById("outfitList").children.length === 7,
    w2.document.getElementById("outfitList").children.length);
  check("and the page says where it came from",
    /Worked out at/.test(w2.document.getElementById("todayFrom").textContent),
    w2.document.getElementById("todayFrom").textContent);

  console.log("\n--- 3. the morning push's advice is the same store --------------");
  const w3 = page();
  w3.localStorage.setItem("oa.today", JSON.stringify({
    ...stored, how: "push", at: Date.now() }));
  await w3.eval("appReady");
  check("opening the app shows what the push already worked out",
    w3.document.getElementById("outfitList").children.length === 7);
  check("and says so, so it is not mistaken for a fresh answer",
    /this morning's push/.test(w3.document.getElementById("todayFrom").textContent),
    w3.document.getElementById("todayFrom").textContent);

  // The Kotlin worker writes this key directly into Capacitor's own store. If the
  // two sides ever disagree the push's advice is silently dropped — no error, just
  // the blank page the user complained about.
  const kt = fs.readFileSync(WORKER, "utf8");
  const jsKey = (fs.readFileSync(HTML, "utf8").match(/const TODAY_KEY="([^"]+)"/) || [])[1];
  const ktKey = (kt.match(/const val KEY_TODAY = "([^"]+)"/) || [])[1];
  check("the phone and the worker agree on the key", jsKey === ktKey, { jsKey, ktKey });
  check("the worker writes to Capacitor's own preference store",
    /getSharedPreferences\("CapacitorStorage"/.test(kt));
  check("and writes the same fields the page reads",
    ["day", "weather", "outfit", "outfit_text", "source"].every(f =>
      new RegExp(`put\\("${f}"`).test(kt)),
    ["day", "weather", "outfit", "outfit_text", "source"].filter(f =>
      !new RegExp(`put\\("${f}"`).test(kt)));
  check("it stores BEFORE posting the notification, which the user can tap at once",
    kt.indexOf("persistToday(prefs, advice)") < kt.indexOf("OutfitNotification.post("));

  console.log("\n--- 4. yesterday's advice is not shown --------------------------");
  const w4 = page();
  w4.localStorage.setItem("oa.today", JSON.stringify({ ...stored, day: "2020-01-01" }));
  await w4.eval("appReady");
  check("a stale day is ignored, not rendered",
    w4.document.getElementById("wxCard").style.display !== "block");
  check("and nothing claims where it came from",
    w4.document.getElementById("todayFrom").style.display === "none");

  console.log("\n--- 5. a rule is parsed once, then stored -----------------------");
  ev(`userRules=[]; state.baseUrl="http://x";`);
  ev(`fetch = async () => ({ ok:true, status:200, json: async () => (
    {kind:"avoid_pair", a:{type:"undershirt",color:"white"},
     b:{type:"t_shirt",color:"white"}, restated:"No white undershirt with a white tee"}) });`);
  w.document.getElementById("rlText").value =
    "I got white V-neck inner + white T recommendation. this combination shall be banned";
  await ev(`addRule()`);
  check("the rule is kept", ev(`userRules.length`) === 1, ev(`userRules`));
  check("in the structured form the server enforces",
    ev(`userRules[0].kind`) === "avoid_pair" && !!ev(`userRules[0].a`), ev(`userRules[0]`));
  check("the user's own words are kept beside it, so the list is readable",
    /white V-neck/.test(ev(`userRules[0].text`)), ev(`userRules[0].text`));
  check("the box is cleared for the next one",
    w.document.getElementById("rlText").value === "");
  check("and it is listed back in plain words",
    /No white undershirt/.test(w.document.getElementById("rlList").textContent),
    w.document.getElementById("rlList").textContent);

  console.log("\n--- 6. feedback that is not a rule is refused -------------------");
  ev(`fetch = async () => ({ ok:false, status:422, json: async () => ({}) });`);
  w.document.getElementById("rlText").value = "I like blue";
  await ev(`addRule()`);
  check("nothing unenforceable is stored", ev(`userRules.length`) === 1, ev(`userRules`));
  check("and the user is told, rather than left believing it was understood",
    /Couldn't turn that into a rule/.test(w.document.getElementById("rlErr").textContent),
    w.document.getElementById("rlErr").textContent);
  check("the text is left in the box so it can be reworded, not retyped",
    w.document.getElementById("rlText").value === "I like blue");

  ev(`fetch = async () => { throw new Error("down"); };`);
  w.document.getElementById("rlText").value = "never brown with black";
  await ev(`addRule()`);
  check("an unreachable advisor says so, and stores nothing",
    ev(`userRules.length`) === 1 &&
    /Can't reach the advisor/.test(w.document.getElementById("rlErr").textContent),
    w.document.getElementById("rlErr").textContent);

  console.log("\n--- 7. the rules ride along with the closet ---------------------");
  ev(`closet=[{id:"itm-1",label:"tee",category:"base",group:"tops",type:"t_shirt",
      roles:["base"],colors:["navy"],warmth:1,formality:["casual"],waterproof:false,count:1}];
      wearLog=[]; trips=[]; __sent=null;
      fetch = async (u,o) => { __sent=JSON.parse(o.body);
        return {ok:true, json: async () => ({weather:${JSON.stringify(WX)},
          outfit:${JSON.stringify(OUTFIT)}, outfit_text:"x", source:"llm"})}; };`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("the request carries the rules", (ev(`__sent.rules`) || []).length === 1,
    ev(`__sent.rules`));
  check("in the server's own shape",
    ev(`__sent.rules[0].kind`) === "avoid_pair", ev(`__sent.rules[0]`));

  // A rule names garments; generic advice has no garments to name.
  ev(`closet=[]; __sent=null;`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("but not when there is no closet to apply them to",
    !ev(`__sent.rules`), ev(`__sent`));

  console.log("\n--- 7b. the MORNING PUSH gets them too --------------------------");
  /* The push had been sending neither the closet nor the rules, so the request that
     matters most was generic advice with a ban it had never been told about — and
     the server logged closet=0/0 on every push while the app's own requests carried
     17 items. Raised by the pre-push reviewer, 2026-08-24. */
  ev(`closet=[{id:"itm-1",label:"tee",category:"base",group:"tops",type:"t_shirt",
      roles:["base"],colors:["navy"],warmth:1,formality:["casual"],waterproof:false,count:1}];
      wearLog=[]; trips=[];
      userRules=[{id:"a",kind:"avoid_pair",a:{type:"undershirt",color:"white"},
                  b:{type:"t_shirt",color:"white"},text:"x"}];`);
  await ev(`savePushPayload()`);
  const pp = JSON.parse(w.localStorage.getItem("oa.pushPayload") || "{}");
  check("the push payload is written", !!pp.at, pp);
  check("it carries the wardrobe", (pp.closet || []).length === 1, pp.closet);
  check("with availability already worked out — no arithmetic left for Kotlin",
    pp.closet[0].availableCount === 1, pp.closet[0]);
  check("and the rules", (pp.rules || []).length === 1, pp.rules);

  // Rules without a closet are meaningless: a rule names garments.
  ev(`closet=[];`);
  await ev(`savePushPayload()`);
  const empty = JSON.parse(w.localStorage.getItem("oa.pushPayload") || "{}");
  check("no closet means no rules either", (empty.rules || []).length === 0, empty);

  /* A TRIP BOUNDARY invalidates the payload abruptly, in a way age cannot see:
     closetPayload() answers "the suitcase" on a trip and "the wardrobe" otherwise,
     so one written at home the evening before a departure is hours old and lists
     clothes that are 800 km away by morning. Raised by the pre-push reviewer. */
  const isoIn = (n) => { const d = new Date(Date.now() + n * 86400000);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; };
  ev(`closet=[{id:"itm-1",label:"tee",category:"base",group:"tops",type:"t_shirt",
      roles:["base"],colors:["navy"],warmth:1,formality:["casual"],waterproof:false,count:1}];
      wearLog=[]; trips=[];`);
  await ev(`savePushPayload()`);
  check("with no trips, the payload stops being valid a week out",
    JSON.parse(w.localStorage.getItem("oa.pushPayload")).validBefore === isoIn(7),
    JSON.parse(w.localStorage.getItem("oa.pushPayload")).validBefore);

  ev(`trips=[{id:"t",start:"${isoIn(2)}",end:"${isoIn(5)}",place:"Osaka",packed:[]}];`);
  await ev(`savePushPayload()`);
  check("a trip starting in two days invalidates it ON the departure day",
    JSON.parse(w.localStorage.getItem("oa.pushPayload")).validBefore === isoIn(2),
    JSON.parse(w.localStorage.getItem("oa.pushPayload")).validBefore);

  // A trip only counts as under way once something is packed — that is what makes
  // closetPayload() answer with the suitcase instead of the wardrobe.
  ev(`trips=[{id:"t",start:"${isoIn(-2)}",end:"${isoIn(1)}",place:"Osaka",
              packed:[{id:"itm-1",qty:1}]}];`);
  await ev(`savePushPayload()`);
  const onTrip = JSON.parse(w.localStorage.getItem("oa.pushPayload"));
  check("and a trip ending tomorrow expires it the day after",
    onTrip.validBefore === isoIn(2), onTrip.validBefore);
  check("the payload says which wardrobe it describes", onTrip.onTrip === true, onTrip);
  check("and while away it holds the SUITCASE, not the wardrobe",
    onTrip.closet.length === 1 && onTrip.closet[0].id === "itm-1", onTrip.closet);
  ev(`trips=[];`);
  await ev(`savePushPayload()`);

  /* EXCLUSIVE. A payload stamped with the departure date is already wrong on that
     morning, so the worker must reject it when the dates are EQUAL — accepting it
     sends the home wardrobe on the first day of the trip, and the suitcase on the
     first day home. Raised by the pre-push reviewer, 2026-08-24. */
  check("and the worker refuses one on its boundary day, not just after it",
    /validBefore/.test(kt) && /today\(\) >= validBefore/.test(kt),
    "the worker treats the stamp as inclusive");

  // The worker must read the very key the app writes, and refuse a stale copy.
  const jsPush = (fs.readFileSync(HTML, "utf8").match(/const PUSH_PAYLOAD_KEY="([^"]+)"/) || [])[1];
  const ktPush = (kt.match(/const val KEY_PUSH_PAYLOAD = "([^"]+)"/) || [])[1];
  check("the phone and the worker agree on the payload key",
    jsPush === ktPush, { jsPush, ktPush });
  check("the worker attaches it to the morning request",
    /body\.put\("closet", closet\)/.test(kt) && /body\.put\("rules", rules\)/.test(kt));
  check("and refuses one too old to describe the wardrobe",
    /PUSH_PAYLOAD_MAX_AGE_MS/.test(kt) && /age !in 0\.\./.test(kt));

  console.log("\n--- 7c. the list cannot outgrow what the server accepts ---------");
  /* A 25th rule was kept in memory while only 24 were persisted — and the in-memory
     copy is the one that gets SENT. AdviceRequest.rules caps at 24, so every advice
     request 422'd until the app was restarted. Raised by the pre-push reviewer. */
  const CAP = ev(`MAX_RULES`);
  const serverCap = Number((fs.readFileSync(
    path.join(__dirname, "..", "..", "server", "schemas.py"), "utf8")
    .match(/rules: list\[dict\] \| None = Field\(None, max_length=(\d+)\)/) || [])[1]);
  check("the phone's cap is the server's cap", CAP === serverCap, { CAP, serverCap });

  ev(`state.baseUrl="http://x";
      userRules=Array.from({length:${CAP}},(_,i)=>({id:"r"+i,kind:"avoid_item",
        a:{type:"jeans"},text:"x"}));
      fetch = async () => ({ ok:true, status:200, json: async () => (
        {kind:"avoid_item", a:{type:"jeans"}, restated:"no jeans"}) });`);
  w.document.getElementById("rlText").value = "never jeans";
  await ev(`addRule()`);
  check("one more is refused rather than kept and then rejected by the server",
    ev(`userRules.length`) === CAP, ev(`userRules.length`));
  check("and the user is told why, with what to do about it",
    /Remove one you no longer need/.test(w.document.getElementById("rlErr").textContent),
    w.document.getElementById("rlErr").textContent);

  // Storage that already holds too many (an older build) is trimmed on load, not
  // trusted — otherwise the same 422 returns on the next launch.
  ev(`userRules=Array.from({length:${CAP}+5},(_,i)=>({id:"x"+i,kind:"avoid_item",
        a:{type:"jeans"},text:"x"}));`);
  await ev(`saveRules()`);
  check("and an over-long list is trimmed rather than sent",
    ev(`userRules.length`) === CAP, ev(`userRules.length`));
  ev(`userRules=[];`);

  console.log("\n--- 8. removing a rule --------------------------------------------");
  ev(`userRules=[{id:"a",kind:"avoid_pair",a:{type:"jeans"},b:{type:"blazer"},
                  restated:"No jeans with a blazer",text:"x"}]; renderRules();`);
  w.document.querySelector('[data-rlrm="0"]').click();
  await new Promise(r => setTimeout(r, 20));
  check("it goes", ev(`userRules.length`) === 0, ev(`userRules`));
  check("and the list says so rather than sitting empty",
    /Nothing banned yet/.test(w.document.getElementById("rlList").textContent));

  console.log("\n--- 9. what to wear, in pictures (user, 2026-08-26) -------------");
  /* The photo was already there, buried under an "Item-by-item" fold beneath a
     paragraph of prose. A name is not how anyone recognises their own clothes, so
     the pictures are the headline now and the reasoning is what folds — it is
     worth reading once, not every morning. */
  const OUT = {inner:"", base:"navy tee", mid:"", outer:"light jacket",
    bottoms:"jeans", footwear:"sneakers", accessories:"", tip:"take a brolly"};
  ev(`renderOutfit(${JSON.stringify(OUT)},"because it is mild","llm",
      {closetUsed:true, picks:{base:"i1", bottoms:"i2"}})`);

  const tiles = [...w.document.querySelectorAll("#wearGrid .wearIt")];
  check("every garment being worn gets a tile",
    tiles.map(t => t.dataset.slot).join() === "base,outer,bottoms,footwear",
    tiles.map(t => t.dataset.slot));
  /* Empty slots are left OUT. "Mid layer — (nothing)" is a tile of nothing to look
     at, and on a warm day half the grid would be blanks. */
  check("empty slots are not given a tile of their own",
    !tiles.some(t => ["inner", "mid", "accessories"].includes(t.dataset.slot)),
    tiles.map(t => t.dataset.slot));
  /* Emptiness is not only "". The on-device recommender writes an absent layer as
     PROSE — "None needed", "None essential", "None — but pack a thin layer for AC
     indoors" — so a trim() test gave a prominent tile to each of the things the
     user is explicitly not wearing, which on a warm day is most of the grid.
     Raised by the pre-push reviewer, 2026-08-26. */
  for (const absent of ["", "   ", "None needed", "None essential", "none",
                        "None — but pack a thin layer for AC indoors"])
    check(`${JSON.stringify(absent)} reads as nothing to wear`,
      ev(`slotIsEmpty(${JSON.stringify(absent)})`), absent);
  check("but a garment that merely starts with those letters does not",
    !ev(`slotIsEmpty("Nonesuch jeans")`));

  ev(`renderOutfit({inner:"None needed", base:"navy tee", mid:"None essential",
      outer:"None — but pack a thin layer for AC indoors", bottoms:"jeans",
      footwear:"sneakers", accessories:"", tip:""},"x","llm",{picks:{}})`);
  check("a warm day's grid holds only what is actually worn",
    [...w.document.querySelectorAll("#wearGrid .wearIt")].map(t => t.dataset.slot).join()
      === "base,bottoms,footwear",
    [...w.document.querySelectorAll("#wearGrid .wearIt")].map(t => t.dataset.slot));
  check("and the fold still accounts for all seven slots, absences included",
    w.document.querySelectorAll("#outfitList li").length === 7);
  check("including the advice attached to an absence",
    /pack a thin layer/.test(w.document.getElementById("outfitList").textContent));

  ev(`renderOutfit(${JSON.stringify(OUT)},"because it is mild","llm",
      {closetUsed:true, picks:{base:"i1", bottoms:"i2"}})`);
  check("each tile names the layer and the garment",
    /Base layer/.test(tiles[0].textContent) && /navy tee/.test(tiles[0].textContent),
    tiles[0].textContent.replace(/\s+/g, " ").trim());
  /* A slot the advisor filled with a generic suggestion is not something the user
     owns, and telling the two apart must not require reading either. */
  check("garments from the closet look different from generic suggestions",
    !tiles[0].classList.contains("gen") && tiles[1].classList.contains("gen"),
    tiles.map(t => `${t.dataset.slot}:${t.className}`));

  /* The photo is the whole point. It arrives asynchronously — a file read per item
     — so the grid renders with the category icon and the picture replaces it. If
     that swap misses, the feature silently degrades to the emoji it was meant to
     replace, and nothing errors. */
  ev(`photoLoad = async (id) => "data:image/jpeg;base64,AAAA";`);
  ev(`renderOutfit(${JSON.stringify(OUT)},"x","llm",{closetUsed:true,picks:{base:"i1"}})`);
  await new Promise(r => setTimeout(r, 20));
  const baseTile = w.document.querySelector('#wearGrid .wearIt[data-slot="base"]');
  check("an owned garment's photo replaces the placeholder icon",
    !!baseTile.querySelector("img") && !baseTile.querySelector(".ph"),
    baseTile.innerHTML.slice(0, 90));
  const outerTile = w.document.querySelector('#wearGrid .wearIt[data-slot="outer"]');
  check("a generic suggestion keeps its icon — there is no photo to show",
    !outerTile.querySelector("img") && !!outerTile.querySelector(".ph"));
  check("the item-by-item list gets the photo too",
    !!w.document.querySelector('#outfitList li[data-slot="base"] img'));

  /* Two renders in flight — tapping refresh, or changing gender, both re-render —
     and the SLOWER one lands last. Addressing the tile by slot alone let the
     previous outfit's photo land on top of a different garment, with nothing to
     show anything had gone wrong. Raised by the pre-push reviewer, 2026-08-26.
     Note the first fix used CSS.escape inside the selector; it does not exist in
     every environment, and the catch swallowed the TypeError so the photo simply
     never appeared — the exact failure this feature exists to end. The id is
     compared in JS instead. */
  ev(`photoLoad = async (id) => {
        if (id === "old") { await new Promise(r => setTimeout(r, 60));
          return "data:image/jpeg;base64,OLD"; }
        return "data:image/jpeg;base64,NEW"; };`);
  ev(`renderOutfit(${JSON.stringify(OUT)},"x","llm",{closetUsed:true,picks:{base:"old"}})`);
  ev(`renderOutfit(${JSON.stringify(OUT)},"x","llm",{closetUsed:true,picks:{base:"new"}})`);
  await new Promise(r => setTimeout(r, 120));
  const raced = w.document.querySelector('#wearGrid .wearIt[data-slot="base"] img');
  check("the CURRENT garment's photo is the one shown",
    !!raced && /NEW$/.test(raced.src), raced && raced.src.slice(-12));
  check("a photo from a superseded render is dropped",
    !raced || !/OLD$/.test(raced.src), raced && raced.src.slice(-12));

  // A missing photo file must leave the icon, not an empty box.
  ev(`photoLoad = async () => null;`);
  ev(`renderOutfit(${JSON.stringify(OUT)},"x","llm",{closetUsed:true,picks:{base:"i1"}})`);
  await new Promise(r => setTimeout(r, 20));
  check("a garment whose photo has gone missing still shows its icon",
    !!w.document.querySelector('#wearGrid .wearIt[data-slot="base"] .ph'));

  console.log("\n--- 10. the reasoning folds, and starts folded ------------------");
  const why = w.document.getElementById("whyDet");
  check("there is a fold for the explanation", !!why);
  check("it is CLOSED on arrival — the pictures are the answer", why.open === false);
  check("the prose is inside it", why.contains(w.document.getElementById("aiText")),
    "the explanation is still in the headline");
  check("and so is the full slot-by-slot list, empty slots included",
    why.contains(w.document.getElementById("outfitList")) &&
    w.document.querySelectorAll("#outfitList li").length === 7,
    w.document.querySelectorAll("#outfitList li").length);
  check("the tip stays outside the fold — one line, worth seeing",
    !why.contains(w.document.getElementById("outfitTip")) &&
    /take a brolly/.test(w.document.getElementById("outfitTip").textContent));

  // No tip: an empty line with a lightbulb on it is worse than no line.
  ev(`renderOutfit(${JSON.stringify({...OUT, tip: ""})},"x","llm",{picks:{}})`);
  check("no tip means no tip line", 
    w.document.getElementById("outfitTip").style.display === "none");

  console.log("\n--- 10b. changing gender re-dresses honestly --------------------");
  /* The on-device recommender knows nothing about the closet, so the garments it
     names are generic. Carrying the previous result along with them kept its
     `picks`, and the grid put the OLD outfit's photos beside the NEW outfit's
     names and marked them owned — wrong on both counts, and convincing. Raised by
     the pre-push reviewer, 2026-08-26. */
  ev(`photoLoad = async () => "data:image/jpeg;base64,OLD";
      lastWeather = ${JSON.stringify(WX)}; lastSource = "llm";`);
  ev(`renderOutfit({base:"navy tee",bottoms:"jeans",tip:""},"x","llm",
      {closetUsed:true, picks:{base:"i1"}, closetSent:true})`);
  await new Promise(r => setTimeout(r, 20));
  check("a closet-backed outfit shows the garment's photo",
    !!w.document.querySelector('#wearGrid .wearIt[data-slot="base"] img'));
  check("and says where it came from",
    w.document.getElementById("srcBadge").textContent === "AI · your closet");

  // A DIFFERENT gender — the same one is now a no-op, deliberately, and clicking it
  // would test the guard rather than the re-render.
  const other = [...w.document.querySelectorAll("#genderSeg button")]
    .find(b => b.dataset.g !== ev("state.gender"));
  ev(`lastRes = {weather:lastWeather, outfit:lastOutfit, text:"x", source:"llm",
                 picks:{base:"i1"}, closetUsed:true, closetSent:true};`);
  other.click();
  await new Promise(r => setTimeout(r, 40));
  check("re-dressing locally drops the old outfit's picks",
    ev(`lastRes.picks`) === null, ev(`lastRes`));
  check("so no photo from the previous outfit survives beside the new names",
    !w.document.querySelector("#wearGrid .wearIt img"));
  check("and every tile is marked as a suggestion, not something owned",
    [...w.document.querySelectorAll("#wearGrid .wearIt")].every(t =>
      t.classList.contains("gen")));
  /* The badge has to move too: "AI · 122B" over an outfit the on-device
     recommender produced credits the wrong author, and it is not an offline
     failure either. */
  check("the badge credits the phone, not the model it no longer came from",
    w.document.getElementById("srcBadge").textContent === "on this phone",
    w.document.getElementById("srcBadge").textContent);
  check("and the kept copy matches what is on screen",
    JSON.parse(w.localStorage.getItem("oa.today") || "{}").source === "local",
    JSON.parse(w.localStorage.getItem("oa.today") || "{}").source);

  // Style feeds the same recommender; it used only to repaint the segment and leave
  // the old outfit on screen under the new label.
  /* Tapping the option already selected changes nothing, so it must cost nothing.
     Without a guard it threw away the closet-backed answer, replaced it with
     generic clothing and saved that over the day's advice. Raised by the pre-push
     reviewer, 2026-08-26. */
  ev(`renderOutfit({base:"navy tee",bottoms:"jeans",tip:""},"x","llm",
      {closetUsed:true, picks:{base:"i1"}, closetSent:true});
      lastSource="llm"; lastRes={...lastRes, picks:{base:"i1"}, closetUsed:true};`);
  // Cleared first, so what this asserts is that the no-op tap wrote nothing —
  // not that an earlier test happened to leave something else behind.
  w.localStorage.setItem("oa.today", JSON.stringify({ day: ev("todayISO()"),
    source: "llm", weather: WX, outfit: OUT, outfit_text: "x", at: Date.now() }));
  const already = w.document.querySelector(`#genderSeg button[data-g="${ev("state.gender")}"]`);
  already.click();
  await new Promise(r => setTimeout(r, 40));
  check("re-tapping the current gender leaves the closet-backed advice alone",
    ev(`lastSource`) === "llm" && !!ev(`lastRes.picks`), 
    { source: ev(`lastSource`), picks: ev(`lastRes.picks`) });
  check("and does not overwrite the day's saved advice",
    JSON.parse(w.localStorage.getItem("oa.today") || "{}").source !== "local",
    JSON.parse(w.localStorage.getItem("oa.today") || "{}").source);

  ev(`lastSource="llm"; lastRes={...lastRes, picks:{base:"i1"}, closetUsed:true};`);
  w.document.querySelectorAll("#styleSeg button")[2].click();
  await new Promise(r => setTimeout(r, 40));
  // What is guaranteed is that the re-render RAN and is honest about it — whether
  // the garments differ depends on the style, and asserting that would be testing
  // the recommender's table, not this handler.
  check("changing style re-dresses through the same path",
    ev(`lastSource`) === "local" && ev(`lastRes.picks`) === null, 
    { source: ev(`lastSource`), picks: ev(`lastRes.picks`) });

  console.log("\n--- 11. the avoid list folds too, and starts folded -------------");
  const rlDet = w.document.getElementById("rlDet");
  check("the list of bans is a fold", !!rlDet && rlDet.tagName === "DETAILS");
  check("closed by default — a ban is set once, then wants to be out of the way",
    rlDet.open === false);
  ev(`userRules=[]; renderRules();`);
  check("with nothing banned the summary is plain",
    w.document.getElementById("rlSum").textContent === "Things to avoid",
    w.document.getElementById("rlSum").textContent);
  ev(`userRules=[{id:"a",kind:"avoid_item",a:{type:"jeans"},restated:"No jeans",text:"x"},
                 {id:"b",kind:"avoid_item",a:{type:"polo"},restated:"No polos",text:"y"}];
      renderRules();`);
  check("the count rides on the summary, so the fold answers 'anything banned?' shut",
    w.document.getElementById("rlSum").textContent === "Things to avoid (2)",
    w.document.getElementById("rlSum").textContent);
  check("and it stays shut when the count changes", rlDet.open === false);
  check("the rules themselves are inside it",
    rlDet.contains(w.document.getElementById("rlList")) &&
    /No jeans/.test(w.document.getElementById("rlList").textContent));
  ev(`userRules=[];`);

  console.log("\n--- 12. 'my closet is complete' (user, 2026-08-27) --------------");
  const TEE = {id:"itm-tee-0001", label:"white t-shirt", category:"base", group:"tops",
    type:"t_shirt", roles:["base"], colors:["white"], warmth:1,
    formality:["casual"], waterproof:false, count:2};
  ev(`closet=[${JSON.stringify(TEE)}]; wearLog=[]; trips=[]; userRules=[]; gaps=[];
      closetComplete=false; __sent=null;
      fetch = async (u,o) => { __sent = JSON.parse(o.body);
        return {ok:true, json: async () => ({weather:${JSON.stringify(WX)},
          outfit:{base:"white t-shirt", outer:"Waterproof shell"}, outfit_text:"x",
          source:"llm", picks:{base:"itm-tee-0001", outer:null},
          closetUsed:true, missing:["outer"]})}; };`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("off by default — a half-registered wardrobe still gets useful hints",
    !ev(`__sent.closetOnly`), ev(`__sent.closetOnly`));

  ev(`closetComplete=true;`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("once ticked, the advisor is told to pick only from what is owned",
    ev(`__sent.closetOnly`) === true, ev(`__sent.closetOnly`));

  /* The flag describes the WARDROBE, not today's laundry. Gating it on what is
     currently wearable turned "only recommend what I own" off on exactly the day
     everything was in the wash — the day a straight answer matters most. Raised by
     the pre-push reviewer, 2026-08-27. */
  ev(`closet=[{...${JSON.stringify(TEE)}, count:1}]; wearLog=[{itemId:"itm-tee-0001",wornAt:Date.now()}];`);
  check("nothing is wearable today", ev(`closetPayload().length`) === 0);
  await ev(`getAdvice(40.3,-74.6)`);
  check("and the flag is still sent", ev(`__sent.closetOnly`) === true, ev(`__sent`));
  await ev(`savePushPayload()`);
  check("the push carries it too, wearable items or not",
    JSON.parse(w.localStorage.getItem("oa.pushPayload")).closetOnly === true);
  ev(`wearLog=[];`);

  // The flag has to reach the MORNING PUSH too, or the notification goes on
  // suggesting garments the user has said they do not own.
  await ev(`savePushPayload()`);
  check("and the morning push is told as well",
    JSON.parse(w.localStorage.getItem("oa.pushPayload")).closetOnly === true,
    JSON.parse(w.localStorage.getItem("oa.pushPayload")).closetOnly);
  /* The worker reads the tickbox from its OWN preference, not out of the wardrobe
     snapshot. The flag is a standing instruction about the wardrobe — it does not
     go stale with a snapshot — and every early return below it (no payload, too
     old, past a trip boundary, nothing wearable) is a morning when generic
     catalogue advice would break the promise most quietly. Raised by the pre-push
     reviewer, 2026-08-27. */
  const jsFlagKey = (fs.readFileSync(HTML, "utf8")
    .match(/prefSet\("(oa\.closetComplete)"/) || [])[1];
  const ktFlagKey = (kt.match(/const val KEY_CLOSET_COMPLETE = "([^"]+)"/) || [])[1];
  check("the phone and the worker agree on the tickbox key",
    jsFlagKey === ktFlagKey, { jsFlagKey, ktFlagKey });
  check("the worker forwards it", /body\.put\("closetOnly", true\)/.test(kt));
  check("before every early return, so no rejection below can drop it",
    ["KEY_PUSH_PAYLOAD, null) ?: return", "today() >= validBefore",
     "if (closet.length() == 0) return"].every(
       marker => kt.indexOf('body.put("closetOnly", true)') < kt.indexOf(marker)),
    "closetOnly is dropped on one of the early-return paths");

  console.log("\n--- 13. what the wardrobe could not cover -----------------------");
  /* Recorded ONLY while the wardrobe is declared complete. Otherwise an empty slot
     means "not photographed yet", not "you do not own one", and a week of that has
     the advisor recommending a coat already hanging up. It is also what the
     tickbox's own text promises. Raised by the pre-push reviewer, 2026-08-27. */
  ev(`gaps=[]; closetComplete=false;`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("an incomplete wardrobe's empty slots are NOT taken as evidence",
    ev(`gaps.length`) === 0, ev(`gaps`));
  ev(`closetComplete=true;`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("a complete one's are", ev(`gaps.length`) >= 1, ev(`gaps`));

  /* Every morning the advisor comes up short, the slot and the day's temperatures
     are written down. This is what the shopping list argues FROM — a gap on eleven
     mornings between 2C and 9C is an argument; "you should own a coat" is not. */
  check("the empty slot was recorded", ev(`gaps.length`) >= 1, ev(`gaps`));
  check("with the weather it happened in",
    ev(`gaps[0].lo`) === WX.lo && ev(`gaps[0].hi`) === WX.hi, ev(`gaps[0]`));
  /* `at` is the planning temperature the server used; `day` is a date with no
     time. No place, no coordinates, no clock — the record is about the wardrobe,
     not about where somebody was on a Tuesday. */
  check("and no place, no time of day — this is about the wardrobe",
    Object.keys(ev(`gaps[0]`)).sort().join() === "at,day,hi,lo,slot",
    Object.keys(ev(`gaps[0]`)));

  // Tapping refresh five times is ONE cold morning, not five. Counting requests
  // would inflate the evidence in proportion to how often the user reloads.
  const before = ev(`gaps.length`);
  await ev(`getAdvice(40.3,-74.6)`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("asking again the same day does not count twice",
    ev(`gaps.length`) === before, ev(`gaps`));

  // A slot the weather made unnecessary is NOT a gap; only what the server named.
  ev(`gaps=[];`);
  await ev(`recordGaps([], ${JSON.stringify(WX)})`);
  check("a day with nothing missing records nothing", ev(`gaps.length`) === 0);

  /* Expiry applies on READ. Pruning only inside saveGaps meant records expired
     only when a NEW gap arrived, so a wardrobe that stopped falling short kept its
     evidence for ever and could still be offered suggestions argued from a winter
     it had already fixed. Raised by the pre-push reviewer, 2026-08-27. */
  ev(`gaps=[{slot:"outer",day:"2020-01-01",lo:2,hi:9},
            {slot:"mid",day:todayISO(),lo:4,hi:11}];`);
  check("evidence past its keep-window is not counted",
    ev(`gapSummary()`).length === 1 && ev(`gapSummary()`)[0].slot === "mid",
    ev(`gapSummary()`));
  check("nor does it make the button think a week has passed",
    ev(`shoppingDays()`) === 1, ev(`shoppingDays()`));

  ev(`gaps=[{slot:"outer",day:"2026-08-01",lo:2,hi:9},
            {slot:"outer",day:"2026-08-02",lo:4,hi:11},
            {slot:"mid",day:"2026-08-02",lo:4,hi:11}];`);
  const sum = ev(`gapSummary()`);
  check("the summary counts mornings per slot",
    sum[0].slot === "outer" && sum[0].n === 2, sum);
  check("and spans the weather they happened in",
    sum[0].loC === 2 && sum[0].hiC === 11, sum[0]);

  /* The server only ever sees what is WEARABLE — closetPayload() drops the
     cooldown, and on a trip it is the suitcase. So a coat in the wash makes `outer`
     look unfillable, and a week of washing days would have the shopping list
     recommending a replacement for a coat already hanging up. Raised by the
     pre-push reviewer, 2026-08-27. */
  ev(`closetComplete=true; gaps=[];
      closet=[{id:"itm-coat-01",label:"coat",category:"outer",group:"outerwear",
               type:"coat",roles:["outer"],colors:[],warmth:5,formality:["casual"],
               waterproof:false,count:1}];`);
  ev(`wearLog=[{itemId:"itm-coat-01",wornAt:Date.now()}];`);
  await ev(`recordGaps(["outer","mid"], ${JSON.stringify(WX)}, 14)`);
  check("a coat that is merely in the wash is not recorded as a gap",
    ev(`gaps.map(g=>g.slot).join()`) === "mid", ev(`JSON.stringify(gaps)`));

  /* Withheld is not the same as CAPABLE. A shell in the wash that the server would
     have refused as too thin excuses nothing — the slot was short whether or not it
     was in the basket. Same for one the wearer has banned. Raised by the pre-push
     reviewer, 2026-08-27. */
  ev(`gaps=[]; closet=[{id:"itm-thin-01",label:"thin shell",category:"outer",
       group:"outerwear",type:"rainwear",roles:["outer"],colors:[],warmth:2,
       formality:["casual"],waterproof:true,count:1}];
      wearLog=[{itemId:"itm-thin-01",wornAt:Date.now()}];`);
  await ev(`recordGaps(["outer"], ${JSON.stringify(WX)}, 4)`);
  check("a withheld shell too thin for the day does not excuse the gap",
    ev(`gaps.length`) === 1, ev(`JSON.stringify(gaps)`));

  ev(`gaps=[];`);
  await ev(`recordGaps(["outer"], ${JSON.stringify(WX)}, 16)`);
  check("but on a mild day, where it would have done, it does",
    ev(`gaps.length`) === 0, ev(`JSON.stringify(gaps)`));

  ev(`gaps=[]; wearLog=[{itemId:"itm-coat-99",wornAt:Date.now()}];
      closet=[{id:"itm-coat-99",label:"banned coat",category:"outer",
       group:"outerwear",type:"coat",roles:["outer"],colors:["white"],warmth:5,
       formality:["casual"],waterproof:false,count:1}];
      userRules=[{kind:"avoid_item",a:{color:"white"}}];`);
  await ev(`recordGaps(["outer"], ${JSON.stringify(WX)}, 4)`);
  check("nor does a withheld garment the wearer has banned",
    ev(`gaps.length`) === 1, ev(`JSON.stringify(gaps)`));
  ev(`userRules=[]; wearLog=[];`);

  /* But owning SOMETHING for the slot is not the test. A shell too thin for
     freezing weather, or an outer layer the wearer has banned, is reported missing
     by a server that HAD the item in front of it and judged it unsuitable — and
     that is the most valuable signal here. Discarding it would mean the shopping
     list could learn "you own no coat" but never "you need a warmer one". Raised by
     the pre-push reviewer, 2026-08-27. */
  ev(`gaps=[]; wearLog=[];`);
  await ev(`recordGaps(["outer"], ${JSON.stringify(WX)})`);
  check("a coat that WAS sent and judged unsuitable is a real gap",
    ev(`gaps.map(g=>g.slot).join()`) === "outer", ev(`JSON.stringify(gaps)`));
  ev(`gaps=[];`);

  /* An OUTAGE is where a broken promise is hardest to notice: everything else on
     the screen looks normal. The on-device recommender dresses from a catalogue, so
     with the closet declared complete it must not run. */
  ev(`closetComplete=true;
      fetch = async () => { throw new Error("DGX down"); };
      fetchWeatherLocal = async () => (${JSON.stringify(WX)});`);
  const off = await ev(`getAdvice(40.3,-74.6)`);
  check("with the advisor down, nothing unowned is suggested",
    Object.entries(off.outfit).every(([k, v]) => k === "tip" || String(v).startsWith("None")),
    off.outfit);
  check("and the PROSE says so too — it is what the notification shows",
    /Nothing to suggest/.test(off.text) && !/coat|jacket/i.test(off.text), off.text);

  ev(`closetComplete=false;`);
  const off2 = await ev(`getAdvice(40.3,-74.6)`);
  check("without the tickbox the offline estimate still helps",
    Object.entries(off2.outfit).some(([k, v]) => k !== "tip" && !String(v).startsWith("None")),
    off2.outfit);
  ev(`closetComplete=true;`);

  console.log("\n--- 13b. the MORNING PUSH's gaps count too ----------------------");
  /* The push is how most advice actually arrives. Recording only in the foreground
     path meant somebody who reads the notification and never taps refresh would
     never accumulate a week — the weekly feature would simply never switch on for
     them. Raised by the pre-push reviewer, 2026-08-27. */
  check("the worker carries the missing slots home",
    /put\("missing", raw\.opt\("missing"\)\)/.test(kt),
    "the push response's gaps are dropped on the floor");

  const w5 = page();
  w5.localStorage.setItem("oa.closetComplete", "1");
  w5.localStorage.setItem("oa.today", JSON.stringify({
    day: new Date().toISOString().slice(0, 10), at: Date.now(), how: "push",
    weather: WX, outfit: OUT, outfit_text: "x", source: "llm",
    picks: {}, closetUsed: true, missing: ["outer", "mid"] }));
  await w5.eval("appReady");
  check("and opening the app records them",
    w5.eval(`gaps.map(g=>g.slot).sort().join()`) === "mid,outer",
    w5.eval(`JSON.stringify(gaps)`));
  check("with the weather from that morning",
    w5.eval(`gaps[0].lo`) === WX.lo, w5.eval(`gaps[0]`));
  // Reading the same stored advice again must not count the morning twice.
  await w5.eval(`loadToday()`);
  check("and reading it again does not count the morning twice",
    w5.eval(`gaps.length`) === 2, w5.eval(`gaps.length`));

  console.log("\n--- 13c. buying the thing settles the argument ------------------");
  /* Evidence is about a wardrobe that no longer exists once something is added to
     it. Seven outer gaps, then a coat arrives — and without this the button stays
     lit and the endpoint is handed seven reasons to recommend another coat. Raised
     by the pre-push reviewer, 2026-08-27. */
  ev(`gaps=[{slot:"outer",day:"2026-08-20",lo:2,hi:9},
            {slot:"mid",day:"2026-08-20",lo:2,hi:9}];`);
  const GAPS = `[{slot:"outer",day:"2026-08-20",lo:2,hi:9},
                 {slot:"mid",day:"2026-08-20",lo:2,hi:9}]`;
  ev(`userRules=[]; gaps=${GAPS};`);
  await ev(`clearGapsFilledBy({roles:["outer"],category:"outer",group:"outerwear",
                               type:"coat",warmth:5})`);
  check("adding a proper coat forgets the outer gaps it answers",
    ev(`gaps.map(g=>g.slot).join()`) === "mid", ev(`JSON.stringify(gaps)`));
  check("and leaves the ones it does not", ev(`gaps.length`) === 1);

  /* But only the gaps it could ACTUALLY have filled. A second warmth-2 shell does
     not answer an outer gap recorded at 2C — the wardrobe is exactly as short as it
     was, and forgetting the evidence would hide that for good. Raised by the
     pre-push reviewer, 2026-08-27. */
  ev(`gaps=${GAPS};`);
  await ev(`clearGapsFilledBy({roles:["outer"],category:"outer",group:"outerwear",
                               type:"rainwear",warmth:2})`);
  check("another thin shell forgets nothing",
    ev(`gaps.length`) === 2, ev(`JSON.stringify(gaps)`));

  ev(`gaps=${GAPS}; userRules=[{kind:"avoid_item",a:{type:"coat"}}];`);
  await ev(`clearGapsFilledBy({roles:["outer"],category:"outer",group:"outerwear",
                               type:"coat",warmth:5})`);
  check("nor does a garment the wearer has banned outright",
    ev(`gaps.length`) === 2, ev(`JSON.stringify(gaps)`));

  /* A ban may name a colour, a group or a role rather than a type. Matching only
     the type let a white coat clear outer gaps while "never wear white" was in
     force — evidence gone, and the server would refuse the coat anyway. Raised by
     the pre-push reviewer, 2026-08-27. */
  for (const [sel, item, why] of [
    [`{color:"white"}`, `{type:"coat",colors:["white"]}`, "a banned COLOUR"],
    [`{group:"outerwear"}`, `{type:"coat",colors:["navy"]}`, "a banned GROUP"],
    [`{role:"outer"}`, `{type:"coat",colors:["navy"]}`, "a banned ROLE"],
  ]) {
    ev(`gaps=${GAPS}; userRules=[{kind:"avoid_item",a:${sel}}];`);
    await ev(`clearGapsFilledBy({roles:["outer"],category:"outer",group:"outerwear",
                                 warmth:5,...${item}})`);
    check(`${why} is recognised, so the evidence is kept`,
      ev(`gaps.length`) === 2, ev(`JSON.stringify(gaps)`));
  }
  // And a rule that does NOT describe the garment must not block a real answer.
  ev(`gaps=${GAPS}; userRules=[{kind:"avoid_item",a:{color:"white"}}];`);
  await ev(`clearGapsFilledBy({roles:["outer"],category:"outer",group:"outerwear",
                               type:"coat",warmth:5,colors:["navy"]})`);
  check("a ban on a colour this garment is not still lets it settle the gap",
    ev(`gaps.length`) === 1, ev(`JSON.stringify(gaps)`));
  ev(`userRules=[];`);

  /* Clearing happens where the user CONFIRMS the item, and only there.
     What /classify returns is provisional — it is why the edit sheet opens next —
     and clearing on it is irreversible: a coat read as a base layer would delete
     the base evidence, and correcting it afterwards cannot bring that back.
     Forgetting evidence wrongly is the expensive mistake. Raised by the pre-push
     reviewer, 2026-08-27. */
  ev(`userRules=[]; closet=[]; wearLog=[]; trips=[];
      gaps=[{slot:"base",day:"2026-08-20",lo:2,hi:9,at:4}];
      capture=async()=>"data:image/jpeg;base64,AAAA"; downscale=async()=>"AAAA";
      photoSave=async()=>true;
      classifyPhoto=async()=>({label:"thing",category:"base",group:"tops",
        type:"t_shirt",roles:["base"],colors:[],warmth:1,formality:["casual"],
        waterproof:false});`);
  await ev(`addItem("camera")`);
  check("a provisional classification does not erase evidence",
    ev(`gaps.length`) === 1, ev(`JSON.stringify(gaps)`));
  ev(`closeSheet&&closeSheet();`);

  ev(`userRules=[]; closet=[]; wearLog=[]; trips=[];
      gaps=[{slot:"outer",day:"2026-08-20",lo:2,hi:9,at:4}];
      sheet={item:{id:"itm-new-001",label:"coat",category:"base",group:"tops",
                   type:"t_shirt",roles:["base"],colors:[],warmth:5,
                   formality:["casual"],waterproof:false,count:1},isNew:false};`);
  w.document.getElementById("shLabel").value = "wool coat";
  w.document.getElementById("shCat").value = "outer";
  w.document.getElementById("shGroup").value = "outerwear";
  const typeSel = w.document.getElementById("shType");
  typeSel.innerHTML = '<option value="coat">Coat</option>';
  typeSel.value = "coat";
  w.document.getElementById("shColors").value = "navy";
  await ev(`document.getElementById("shSave").onclick()`);
  check("correcting a misclassified item settles the gaps it answers",
    ev(`gaps.length`) === 0, ev(`JSON.stringify(gaps)`));

  /* Judged at the PLANNING temperature the server used, not the overnight low.
     They cross the warmth thresholds on different days, so the wrong one forgets
     gaps the server would still raise — or keeps ones it would not. */
  ev(`gaps=[{slot:"outer",day:"2026-08-20",lo:2,hi:14,at:13}];`);
  await ev(`clearGapsFilledBy({roles:["outer"],category:"outer",group:"outerwear",
                               type:"jacket",warmth:3})`);
  check("a warmth-3 jacket answers a gap planned at 13C",
    ev(`gaps.length`) === 0, ev(`JSON.stringify(gaps)`));
  ev(`gaps=[{slot:"outer",day:"2026-08-20",lo:2,hi:14,at:4}];`);
  await ev(`clearGapsFilledBy({roles:["outer"],category:"outer",group:"outerwear",
                               type:"jacket",warmth:3})`);
  check("but not one planned at 4C, where the server wants warmth 4",
    ev(`gaps.length`) === 1, ev(`JSON.stringify(gaps)`));

  /* The warmth table is a TWIN of _OUTER_MIN_WARMTH in server/picks.py. If they
     drift, the evidence and the advice disagree about the same wardrobe: the app
     forgets a gap the server would still raise, or keeps one it would not. */
  const serverLine = (fs.readFileSync(
    path.join(__dirname, "..", "..", "server", "picks.py"), "utf8")
    .split("\n").find(l => l.startsWith("_OUTER_MIN_WARMTH")) || "");
  const serverPairs = [...serverLine.matchAll(/\((\d+),\s*(\d+)\)/g)]
    .map(m => [Number(m[1]), Number(m[2])]);
  check("the phone's warmth table matches the server's",
    JSON.stringify(ev(`OUTER_MIN_WARMTH`)) === JSON.stringify(serverPairs),
    { phone: ev(`OUTER_MIN_WARMTH`), server: serverPairs });

  console.log("\n--- 13d. mornings the push saw while the app was shut -----------");
  /* oa.today holds ONE day and is overwritten by the next push. Somebody who reads
     the notification and never opens the app therefore lost every morning but the
     last, and could never reach the week the shopping list needs — the ordinary
     usage pattern defeated the feature. Raised by the pre-push reviewer,
     2026-08-27. */
  const jsQ = (fs.readFileSync(HTML, "utf8")
    .match(/const GAPS_PENDING_KEY="([^"]+)"/) || [])[1];
  const ktQ = (kt.match(/const val KEY_GAPS_PENDING = "([^"]+)"/) || [])[1];
  check("the phone and the worker agree on the queue key", jsQ === ktQ, { jsQ, ktQ });
  check("the worker appends rather than overwriting",
    /queueGaps\(prefs, raw, out\.getString\("day"\)\)/.test(kt));
  check("and one entry per day, so a retry does not count twice",
    /if \(e\.optString\("day"\) != day\) out\.put\(e\)/.test(kt));
  check("bounded, so an app unopened for months does not grow it for ever",
    /PENDING_MAX/.test(kt));

  const w6 = page();
  w6.localStorage.setItem("oa.closetComplete", "1");
  w6.localStorage.setItem("oa.gapsPending", JSON.stringify([
    { day: "2026-08-21", missing: ["outer"], lo: 2, hi: 9, planTemp: 4 },
    { day: "2026-08-22", missing: ["outer", "mid"], lo: 3, hi: 10, planTemp: 5 }]));
  await w6.eval("appReady");
  check("every queued morning is recorded, not just the last",
    w6.eval(`shoppingDays()`) === 2, w6.eval(`JSON.stringify(gaps)`));
  check("each with the weather and planning temperature of ITS morning",
    w6.eval(`gaps.find(g=>g.day==="2026-08-22").at`) === 5,
    w6.eval(`JSON.stringify(gaps)`));
  check("and the queue is emptied, so a later open does not double-count",
    w6.localStorage.getItem("oa.gapsPending") === "[]",
    w6.localStorage.getItem("oa.gapsPending"));

  /* A push can append BETWEEN the read and the write — the app being opened while
     one finishes is not exotic, it is the moment somebody taps the notification.
     Clearing the key outright erased a morning that had never been recorded.
     Raised by the pre-push reviewer, 2026-08-27. */
  const w7 = page();
  w7.localStorage.setItem("oa.closetComplete", "1");
  await w7.eval("appReady");
  w7.eval(`
    gaps = [];
    localStorage.setItem("oa.gapsPending", JSON.stringify(
      [{day:"2026-08-21", missing:["outer"], lo:2, hi:9, planTemp:4, sent:[]}]));
    const realGet = prefGet;
    let first = true;
    prefGet = async (k, d) => {
      if (k === "oa.gapsPending" && first) {
        first = false;
        const v = localStorage.getItem(k) || d;
        // the worker lands a new morning while we are reading
        localStorage.setItem(k, JSON.stringify([...JSON.parse(v),
          {day:"2026-08-22", missing:["mid"], lo:3, hi:10, planTemp:5, sent:[]}]));
        return v;
      }
      return realGet(k, d);
    };`);
  await w7.eval(`drainPendingGaps()`);
  check("a morning queued mid-drain is not erased unrecorded",
    /2026-08-22/.test(w7.localStorage.getItem("oa.gapsPending")),
    w7.localStorage.getItem("oa.gapsPending"));
  check("and the one that WAS drained is gone",
    !/2026-08-21/.test(w7.localStorage.getItem("oa.gapsPending")),
    w7.localStorage.getItem("oa.gapsPending"));

  /* A queued morning is judged by the availability of THAT morning. The drain
     happens later — by which time the laundry has moved on — so using today's
     would turn a coat that was in the wash into one that was never owned, or the
     reverse. The worker records which items it actually sent. Raised by the
     pre-push reviewer, 2026-08-27. */
  check("the worker records what it sent", /\.put\("sent", sentIds/.test(kt));
  const COAT = {id:"itm-coat-01", label:"wool coat", category:"outer",
    group:"outerwear", type:"coat", roles:["outer"], colors:["navy"], warmth:5,
    formality:["casual"], waterproof:false, count:1};
  for (const [sent, wantGaps, why] of [
    [[], 0, "the coat was in the wash that morning, so the slot proves nothing"],
    [["itm-coat-01"], 1, "the coat WAS sent and the slot was still short"],
  ]) {
    const wx = page();
    wx.localStorage.setItem("oa.closetComplete", "1");
    wx.localStorage.setItem("oa.closet", JSON.stringify([COAT]));
    wx.localStorage.setItem("oa.gapsPending", JSON.stringify([
      { day: "2026-08-21", missing: ["outer"], lo: 2, hi: 9, planTemp: 4, sent }]));
    await wx.eval("appReady");
    check(why, wx.eval(`gaps.length`) === wantGaps, wx.eval(`JSON.stringify(gaps)`));
  }

  /* And the rules must be loaded BEFORE the drain, because judging a queued
     morning asks whether a withheld garment was banned. */
  const src = fs.readFileSync(HTML, "utf8");
  check("the rules are restored before the queue is drained",
    src.indexOf('prefGet("oa.rules"') < src.lastIndexOf("await drainPendingGaps()"),
    "a banned garment would count as a suitable alternative on every cold start");
  check("and so is the closet", 
    src.indexOf('prefGet("oa.closet"') < src.lastIndexOf("await drainPendingGaps()"));

  console.log("\n--- 14. purchase suggestions ------------------------------------");
  /* Gated on a week of evidence. The user asked for this WEEKLY, and fewer
     mornings than that would be a catalogue dressed up as an argument. */
  ev(`gaps=[{slot:"outer",day:"2026-08-01",lo:2,hi:9}]; refreshShopping();`);
  check("not offered before there is anything to argue from",
    w.document.getElementById("shopBtn").disabled === true);
  check("and it says how much is still needed, rather than just greying out",
    /a week of mornings/.test(w.document.getElementById("shopNote").textContent),
    w.document.getElementById("shopNote").textContent);

  /* Recording the seventh morning must OPEN the feature, then and there. Without
     a refresh the button stayed disabled and its count stale until some unrelated
     closet action or a relaunch — the feature would appear a day late for no
     reason the user could see. Raised by the pre-push reviewer, 2026-08-27. */
  ev(`closetComplete=true;
      gaps=Array.from({length:6},(_,i)=>({slot:"outer",
        day:"2026-08-"+String(10+i).padStart(2,"0"), lo:2, hi:9}));
      refreshShopping();`);
  check("six mornings is not yet a week", w.document.getElementById("shopBtn").disabled);
  // A slot the wardrobe genuinely cannot fill — the coat above covers `outer`, so
  // recording that one would (correctly) be filtered out as a laundry gap.
  await ev(`recordGaps(["accessories"], ${JSON.stringify(WX)})`);
  check("recording the seventh opens it immediately, with no reload",
    w.document.getElementById("shopBtn").disabled === false,
    w.document.getElementById("shopNote").textContent);

  /* Tied to the tickbox, not only to the evidence. Untick it and the wardrobe may
     be partial again, so suggestions argued from the old record would recommend
     clothes already hanging up but not yet photographed. The evidence is KEPT — it
     was true when collected — it simply stops being answered from. */
  ev(`gaps=Array.from({length:9},(_,i)=>({slot:"outer",
        day:"2026-08-"+String(10+i).padStart(2,"0"), lo:2, hi:9}));
      closetComplete=false; refreshShopping();`);
  check("a week of evidence is not enough while the wardrobe is declared partial",
    w.document.getElementById("shopBtn").disabled === true);
  check("and the note says what to do about it",
    /My closet is complete/.test(w.document.getElementById("shopNote").textContent),
    w.document.getElementById("shopNote").textContent);
  check("the evidence itself is kept, not thrown away", ev(`gaps.length`) === 9);

  ev(`closetComplete=true; refreshShopping();`);
  check("offered once a week of mornings has gone wrong",
    w.document.getElementById("shopBtn").disabled === false);
  check("and it says what it is arguing from",
    /9 mornings/.test(w.document.getElementById("shopNote").textContent),
    w.document.getElementById("shopNote").textContent);

  ev(`__sent=null; fetch = async (u,o) => { __sent=JSON.parse(o.body);
      return {ok:true, json: async () => ({suggestions:[
        {what:"wool overcoat", slot:"outer", why:"empty on nine mornings", priority:1}],
        verdict:"One real gap."})}; };`);
  await ev(`askShopping()`);
  /* The WHOLE wardrobe, not what is wearable today. closetPayload() drops the
     laundry and becomes the suitcase on a trip — sending it would let the advisor
     recommend a coat hanging at home because it happened to be in the wash, which
     is the one thing this endpoint must not do. Raised by the pre-push reviewer. */
  check("the request describes what they OWN, not what is clean",
    (ev(`__sent.closet`) || []).length === ev(`closet.length`),
    { sent: (ev(`__sent.closet`) || []).length, owned: ev(`closet.length`) });
  check("the request carries the evidence, not just the closet",
    (ev(`__sent.gaps`) || []).length === 1 && ev(`__sent.gaps[0].n`) === 9,
    ev(`__sent.gaps`));
  check("and the thermal calibration — someone who runs cold needs warmth, not a shirt",
    ev(`"tempOffset" in __sent`), Object.keys(ev(`__sent`)));
  check("the suggestion is shown with its reason",
    /wool overcoat/.test(w.document.getElementById("shopOut").textContent) &&
    /nine mornings/.test(w.document.getElementById("shopOut").textContent),
    w.document.getElementById("shopOut").textContent.slice(0, 120));

  // "Nothing to buy" is a real answer, and the one a good wardrobe should get.
  ev(`fetch = async () => ({ok:true, json: async () => (
      {suggestions:[], verdict:"Nothing missing — your closet covers it."})});`);
  await ev(`askShopping()`);
  check("an empty answer is stated, not left blank",
    /Nothing missing/.test(w.document.getElementById("shopOut").textContent),
    w.document.getElementById("shopOut").textContent);

  ev(`fetch = async () => { throw new Error("down"); };`);
  await ev(`askShopping()`);
  check("an unreachable advisor says so rather than showing an empty list",
    /Couldn't reach the advisor/.test(w.document.getElementById("shopOut").textContent),
    w.document.getElementById("shopOut").textContent);

  console.log("\n--- 15. telling it what you wore instead (2026-08-29) -----------");
  /* The best evidence the app can collect: somebody who read the suggestion,
     disagreed, and put on something else has named BOTH the garment they wanted and
     the one it beat. */
  const WTEE = {id:"itm-tee-0001", label:"white tee", category:"base", group:"tops",
    type:"t_shirt", roles:["base"], colors:[], warmth:1, formality:["casual"],
    waterproof:false, count:2};
  const POLO = {id:"itm-polo-001", label:"navy polo", category:"base", group:"tops",
    type:"polo", roles:["base"], colors:[], warmth:2, formality:["smart"],
    waterproof:false, count:2};
  ev(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}];
      wearLog=[]; trips=[]; swaps=[]; userRules=[]; closetComplete=false;
      lastOutfit={base:"white tee"}; lastRes={picks:{base:"itm-tee-0001"}};
      lastPickIds=["itm-tee-0001"]; wornLogged=false;`);
  ev(`openWoreSheet()`);
  const sel = w.document.querySelector('[data-wore="base"]');
  check("the sheet offers a row for the slot", !!sel);
  check("prefilled with what was suggested", sel.value === "itm-tee-0001", sel.value);
  check("and only garments that can play that role",
    [...sel.options].map(o => o.value).filter(Boolean).sort().join() ===
      "itm-polo-001,itm-tee-0001",
    [...sel.options].map(o => o.value));

  sel.value = "itm-polo-001"; sel.onchange();
  await ev(`saveWore()`);
  check("the swap is recorded with what it beat",
    ev(`swaps[0].wore`) === "itm-polo-001" && ev(`swaps[0].instead`) === "itm-tee-0001",
    ev(`JSON.stringify(swaps)`));
  /* The laundry follows the garment actually put on, not the one proposed. */
  check("the garment worn goes to the laundry pile",
    ev(`activeWears("itm-polo-001")`) === 1);
  check("and the one that was only suggested does not",
    ev(`activeWears("itm-tee-0001")`) === 0);

  /* An unavailable SUGGESTION is still offered. Tapping "Wearing it" for the only
     copy is enough to make the rotation call it unavailable — and left out of the
     options, the row silently showed "— nothing —" while the draft still held the
     item, so saving an untouched sheet logged a garment the screen said was not
     worn. Raised by the pre-push reviewer, 2026-08-29. */
  ev(`closet=[${JSON.stringify({...WTEE, count: 1})}];
      wearLog=[{itemId:"itm-tee-0001",wornAt:Date.now()}]; woreLogged=null;
      lastRes={picks:{base:"itm-tee-0001"}}; lastPickIds=["itm-tee-0001"]; wornLogged=true;`);
  ev(`openWoreSheet()`);
  const unavail = w.document.querySelector('[data-wore="base"]');
  check("a suggestion the rotation calls unavailable is still offered",
    [...unavail.options].some(o => o.value === "itm-tee-0001"),
    [...unavail.options].map(o => o.value));
  check("the row shows it, and the draft agrees with the row",
    unavail.value === "itm-tee-0001" && ev(`woreDraft.base`) === "itm-tee-0001",
    { shown: unavail.value, draft: ev(`woreDraft.base`) });

  /* One garment is worn in ONE place. A shirt that plays base or mid appears in
     both rows, and nothing stopped it being chosen twice — recording a preference
     for an outfit nobody could put on, and one the server rejects outright. */
  const OXFORD = {id:"itm-shirt-01", label:"oxford", category:"base", group:"tops",
    type:"shirt", roles:["base","mid"], colors:[], warmth:2, formality:["smart"],
    waterproof:false, count:2};
  ev(`closet=[${JSON.stringify(OXFORD)}]; wearLog=[]; swaps=[]; woreLogged=null;
      lastOutfit={base:"oxford"}; lastRes={picks:{base:"itm-shirt-01"}};
      lastPickIds=["itm-shirt-01"]; wornLogged=false;`);
  ev(`openWoreSheet()`);
  const midSel = w.document.querySelector('[data-wore="mid"]');
  midSel.value = "itm-shirt-01"; midSel.onchange();
  await ev(`saveWore()`);
  check("wearing one garment in two places is refused",
    /one place at a time/.test(w.document.getElementById("woreErr").textContent),
    w.document.getElementById("woreErr").textContent);
  check("and nothing is recorded from it", ev(`swaps.length`) === 0, ev(`swaps`));
  midSel.value = ""; midSel.onchange();
  await ev(`saveWore()`);
  check("correcting the clash lets it save",
    !w.document.getElementById("woreWrap").classList.contains("show"));

  ev(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[];`);

  /* Saving twice — or a double-tap while the first save is in flight — appended
     the same morning again, and swapSummary counts RECORDS: one day would have met
     the two-occasion bar on its own and been reported as a habit. Raised by the
     pre-push reviewer, 2026-08-29. */
  ev(`swaps=[]; lastRes={picks:{base:"itm-tee-0001"}}; lastPickIds=["itm-tee-0001"];
      wornLogged=false; woreDraft={base:"itm-polo-001"};`);
  await ev(`saveWore()`);
  ev(`woreDraft={base:"itm-polo-001"};`);
  await ev(`saveWore()`);
  check("saving the same morning twice records it once",
    ev(`swaps.length`) === 1, ev(`JSON.stringify(swaps)`));
  check("so one day cannot pass for a habit",
    ev(`swapSummary()`).length === 0, ev(`swapSummary()`));

  /* Reopening shows what the app CURRENTLY believes, not the suggestion that was
     overruled. A count-one garment becomes unavailable the moment it is logged, so
     without this it vanished from its own row, the sheet reseeded from the original
     picks, and the next save silently replaced a correctly recorded outfit. Raised
     by the pre-push reviewer, 2026-08-29. */
  ev(`closet=[${JSON.stringify({...WTEE, count: 1})},${JSON.stringify({...POLO, count: 1})}];
      wearLog=[]; swaps=[]; trips=[]; woreLogged=null;
      lastOutfit={base:"white tee"}; lastRes={picks:{base:"itm-tee-0001"}};
      lastPickIds=["itm-tee-0001"]; wornLogged=false;`);
  ev(`openWoreSheet()`);
  const reSel = () => w.document.querySelector('[data-wore="base"]');
  reSel().value = "itm-polo-001"; reSel().onchange();
  await ev(`saveWore()`);
  check("the corrected garment is now unavailable — that is what logging means",
    ev(`avail(closet[1])`) === 0);
  ev(`openWoreSheet()`);
  check("reopening shows what was logged, not what was suggested",
    reSel().value === "itm-polo-001", reSel().value);
  check("and it is still offered despite being unavailable",
    [...reSel().options].some(o => o.value === "itm-polo-001"),
    [...reSel().options].map(o => o.textContent));
  check("the original suggestion is still there too, and still labelled",
    [...reSel().options].some(o => /white tee \(suggested\)/.test(o.textContent)),
    [...reSel().options].map(o => o.textContent));
  await ev(`saveWore()`);
  check("so saving again keeps the outfit rather than replacing it",
    ev(`swaps.length`) === 1 && ev(`swaps[0].wore`) === "itm-polo-001",
    ev(`JSON.stringify(swaps)`));
  ev(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[]; swaps=[];
      woreLogged=null;`);

  /* And it survives a restart, because it describes the wear log — which is on
     disk. Held only in memory, a restart left the app believing the suggestion had
     been worn while the rotation still carried the correction: reopening offered
     the original outfit, and saving it logged the suggestion ON TOP of the garment
     already counted. Raised by the pre-push reviewer, 2026-08-29. */
  const carried = {};
  for (const k of ["oa.woreToday", "oa.closet", "oa.wearlog", "oa.swaps"])
    if (w.localStorage.getItem(k) != null) carried[k] = w.localStorage.getItem(k);
  const w8 = page();
  for (const k in carried) w8.localStorage.setItem(k, carried[k]);
  await w8.eval("appReady");
  check("the correction survives a restart",
    (w8.eval(`woreLogged`) || {}).base === "itm-polo-001",
    w8.eval(`JSON.stringify(woreLogged)`));

  /* And editing it after the restart must RELEASE what it previously logged.
     wornLogged is false on a fresh start while the garments are still counted, so
     relying on the flag alone left the old outfit in the rotation and added the new
     one beside it — both in the laundry, neither correct. Raised by the pre-push
     reviewer, 2026-08-29. */
  const OXFORD2 = {id:"itm-oxfrd-01", label:"oxford", category:"base", group:"tops",
    type:"shirt", roles:["base"], colors:[], warmth:2, formality:["smart"],
    waterproof:false, count:2};
  w8.eval(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)},${JSON.stringify(OXFORD2)}];
           lastOutfit={base:"white tee"}; lastRes={picks:{base:"itm-tee-0001"}};
           lastPickIds=["itm-tee-0001"];`);
  check("the restored correction is still in the rotation",
    w8.eval(`activeWears("itm-polo-001")`) === 1);
  /* And the button has to say so. Left reading "Wearing it" over an outfit already
     logged, the next tap logged the SUGGESTION on top of the correction and
     overwrote the record — an ordinary tap on a screen that looked untouched.
     Raised by the pre-push reviewer, 2026-08-29. */
  check("and the button says the outfit is logged",
    /tap to undo/.test(w8.document.getElementById("dWear").textContent),
    w8.document.getElementById("dWear").textContent);
  w8.eval(`woreDraft={base:"itm-oxfrd-01"};`);
  await w8.eval(`saveWore()`);
  check("changing it releases the garment it replaces",
    w8.eval(`activeWears("itm-polo-001")`) === 0);
  check("and counts only the new one",
    w8.eval(`activeWears("itm-oxfrd-01")`) === 1);

  // Yesterday's correction is about a different outfit, not a stale version of
  // today's, so it must not be restored.
  const w9 = page();
  for (const k in carried) w9.localStorage.setItem(k, carried[k]);
  w9.localStorage.setItem("oa.woreToday", JSON.stringify(
    { day: "2020-01-01", map: { base: "itm-polo-001" } }));
  await w9.eval("appReady");
  check("but yesterday's is not", w9.eval(`woreLogged`) === null,
    w9.eval(`JSON.stringify(woreLogged)`));

  /* Tapping "Wearing it" is the OTHER way today's outfit gets logged, and it has to
     leave the same record. It did not, so after a restart a correction released
     nothing: the suggestion stayed in the laundry and the corrected outfit was
     counted beside it. Raised by the pre-push reviewer, 2026-08-29. */
  const wA = page();
  await wA.eval("appReady");
  wA.eval(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[];
           swaps=[]; trips=[]; lastRes={picks:{base:"itm-tee-0001"}};
           lastPickIds=["itm-tee-0001"]; wornLogged=false; woreLogged=null;`);
  await wA.eval(`document.getElementById("dWear").onclick()`);
  const kept = {};
  for (const k of ["oa.woreToday", "oa.closet", "oa.wearlog", "oa.swaps"])
    if (wA.localStorage.getItem(k) != null) kept[k] = wA.localStorage.getItem(k);
  const wB = page();
  for (const k in kept) wB.localStorage.setItem(k, kept[k]);
  await wB.eval("appReady");
  wB.eval(`lastOutfit={base:"white tee"}; lastRes={picks:{base:"itm-tee-0001"}};
           lastPickIds=["itm-tee-0001"];`);
  check("what 'Wearing it' logged survives the restart as a record",
    wB.eval(`activeWears("itm-tee-0001")`) === 1 &&
    (wB.eval(`woreLogged`) || {}).base === "itm-tee-0001",
    wB.eval(`JSON.stringify(woreLogged)`));
  wB.eval(`woreDraft={base:"itm-polo-001"};`);
  await wB.eval(`saveWore()`);
  check("so correcting it afterwards releases the suggestion",
    wB.eval(`activeWears("itm-tee-0001")`) === 0);
  check("and leaves only what was actually worn",
    wB.eval(`activeWears("itm-polo-001")`) === 1);

  /* Undo after a restart takes back what is ACTUALLY in the laundry. By the
     suggestion, it released a garment that was never logged and left the corrected
     outfit counted — the button said undone and the rotation disagreed. */
  const wE = page();
  await wE.eval("appReady");
  wE.eval(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[];
           swaps=[]; trips=[]; lastRes={picks:{base:"itm-tee-0001"}};
           lastPickIds=["itm-tee-0001"]; wornLogged=false; woreLogged=null;
           woreDraft={base:"itm-polo-001"};`);
  await wE.eval(`saveWore()`);
  const carriedE = {};
  for (const k of ["oa.woreToday", "oa.closet", "oa.wearlog", "oa.swaps"])
    if (wE.localStorage.getItem(k) != null) carriedE[k] = wE.localStorage.getItem(k);
  const wF = page();
  for (const k in carriedE) wF.localStorage.setItem(k, carriedE[k]);
  await wF.eval("appReady");
  wF.eval(`lastRes={picks:{base:"itm-tee-0001"}}; lastPickIds=["itm-tee-0001"];`);
  await wF.eval(`document.getElementById("dWear").onclick()`);
  check("undoing after a restart releases what was actually worn",
    wF.eval(`activeWears("itm-polo-001")`) === 0,
    wF.eval(`JSON.stringify(wearLog)`));
  check("and forgets the correction rather than leaving it on disk",
    wF.eval(`woreLogged`) === null &&
    JSON.parse(wF.localStorage.getItem("oa.woreToday") || "null") === null,
    wF.localStorage.getItem("oa.woreToday"));
  check("and the swap it taught is retracted too", wF.eval(`swaps.length`) === 0,
    wF.eval(`JSON.stringify(swaps)`));

  /* Two taps in the time one save takes. Both reach the wear log before either sets
     the flags, so every garment was counted twice and a two-copy item could leave
     the rotation on the strength of a single morning. Raised by the pre-push
     reviewer, 2026-08-29. */
  const wC = page();
  await wC.eval("appReady");
  wC.eval(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[];
           swaps=[]; trips=[]; lastRes={picks:{base:"itm-tee-0001"}};
           lastPickIds=["itm-tee-0001"]; wornLogged=false; woreLogged=null;
           woreDraft={base:"itm-polo-001"};`);
  await Promise.all([wC.eval(`saveWore()`), wC.eval(`saveWore()`)]);
  check("a double-tap logs the garment once",
    wC.eval(`activeWears("itm-polo-001")`) === 1,
    wC.eval(`activeWears("itm-polo-001")`));
  check("and records one swap, not two",
    wC.eval(`swaps.length`) === 1, wC.eval(`JSON.stringify(swaps)`));

  /* The button toggle is the same shape of race, between two DIFFERENT branches:
     the first tap logs and awaits its write while the second enters the undo. The
     writes finished out of order, leaving the wear log emptied and the record still
     saying logged — which the next launch restored. Raised by the pre-push
     reviewer, 2026-08-29. */
  const wH = page();
  await wH.eval("appReady");
  wH.eval(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[];
           swaps=[]; trips=[]; lastRes={closetUsed:true,picks:{base:"itm-tee-0001"}};
           lastPickIds=["itm-tee-0001"]; wornLogged=false; woreLogged=null;`);
  const tap = () => wH.eval(`document.getElementById("dWear").onclick()`);
  await Promise.all([tap(), tap()]);
  check("a double-tap of the button logs once",
    wH.eval(`activeWears("itm-tee-0001")`) === 1,
    wH.eval(`JSON.stringify(wearLog)`));
  check("and the record agrees with the wear log",
    (wH.eval(`woreLogged`) || {}).base === "itm-tee-0001" &&
    JSON.parse(wH.localStorage.getItem("oa.woreToday") || "null").map.base
      === "itm-tee-0001",
    wH.localStorage.getItem("oa.woreToday"));
  await Promise.all([tap(), tap()]);
  check("and undoing twice undoes once",
    wH.eval(`activeWears("itm-tee-0001")`) === 0 && wH.eval(`woreLogged`) === null,
    wH.eval(`JSON.stringify(wearLog)`));
  check("leaving nothing on disk for the next launch to restore",
    JSON.parse(wH.localStorage.getItem("oa.woreToday") || "null") === null,
    wH.localStorage.getItem("oa.woreToday"));

  /* New advice later the same day does NOT unwear what was already worn. Clearing
     the record while its entries stayed in the wear log orphaned them: nothing could
     find them, undo released the wrong garments, and saving the next outfit counted
     a second one on the same morning. Raised by the pre-push reviewer, 2026-08-29. */
  const wD = page();
  await wD.eval("appReady");
  wD.eval(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[];
           swaps=[]; trips=[]; lastRes={picks:{base:"itm-tee-0001"}};
           lastPickIds=["itm-tee-0001"]; wornLogged=false; woreLogged=null;
           woreDraft={base:"itm-polo-001"};`);
  await wD.eval(`saveWore()`);
  wD.eval(`renderOutfit({base:"white tee"},"",{},
    {closetUsed:true,picks:{base:"itm-tee-0001"}})`);
  check("fresh advice leaves this morning's clothes in the laundry",
    wD.eval(`activeWears("itm-polo-001")`) === 1);
  check("and keeps the record that can find them",
    (wD.eval(`woreLogged`) || {}).base === "itm-polo-001",
    wD.eval(`JSON.stringify(woreLogged)`));
  check("so the button still offers to undo, not to log a second outfit",
    /tap to undo/.test(wD.document.getElementById("dWear").textContent),
    wD.document.getElementById("dWear").textContent);
  wD.eval(`woreDraft={base:"itm-tee-0001"};`);
  await wD.eval(`saveWore()`);
  check("and correcting against the new advice counts one outfit, not two",
    wD.eval(`activeWears("itm-polo-001")`) === 0 &&
    wD.eval(`activeWears("itm-tee-0001")`) === 1,
    wD.eval(`JSON.stringify(wearLog)`));

  /* Even when the later advice has nothing of theirs in it. Hiding the button on
     empty picks took the only way to undo off the screen while the clothes were
     still in the laundry. Raised by the pre-push reviewer, 2026-08-29. */
  wD.eval(`renderOutfit({base:"any dark shirt"},"",{},{closetUsed:false,picks:{}})`);
  check("generic advice still offers to undo this morning's record",
    wD.document.getElementById("dWear").style.display !== "none" &&
    /tap to undo/.test(wD.document.getElementById("dWear").textContent),
    wD.document.getElementById("dWear").style.display);
  await wD.eval(`document.getElementById("dWear").onclick()`);
  check("and undo works with no picks to go on",
    wD.eval(`activeWears("itm-tee-0001")`) === 0 && wD.eval(`woreLogged`) === null,
    wD.eval(`JSON.stringify(wearLog)`));
  check("then it hides, there being nothing left to log or undo",
    wD.document.getElementById("dWear").style.display === "none");

  /* Left open across midnight, the record in memory was still yesterday's — the
     stored copy is day-stamped, the variable was not. The button went on saying
     today's outfit was logged and refused to log it. Raised by the pre-push
     reviewer, 2026-08-29. */
  const wG = page();
  await wG.eval("appReady");
  wG.eval(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[];
           swaps=[]; trips=[]; lastRes={closetUsed:true,picks:{base:"itm-tee-0001"}};
           lastPickIds=["itm-tee-0001"]; wornLogged=false; woreLogged=null;
           woreDraft={base:"itm-polo-001"};`);
  await wG.eval(`saveWore()`);
  // Midnight passes with the app still open: yesterday's wear is a day old, and the
  // record in memory is about a day that has ended.
  wG.eval(`wearLog=wearLog.map(x=>({...x,wornAt:x.wornAt-25*3600*1000}));
           woreDay="2020-01-01";`);
  wG.eval(`syncWearBtn()`);
  check("a record from yesterday retires itself",
    wG.eval(`woreLogged`) === null && wG.eval(`wornLogged`) === false,
    wG.eval(`JSON.stringify(woreLogged)`));
  check("so today's outfit can be logged normally",
    /update my rotation/.test(wG.document.getElementById("dWear").textContent),
    wG.document.getElementById("dWear").textContent);
  wG.eval(`lastOutfit={base:"white tee"};
    renderOutfit(lastOutfit,"",{},{closetUsed:true,picks:{base:"itm-tee-0001"}})`);
  await wG.eval(`document.getElementById("dWear").onclick()`);
  check("and logging counts today's clothes",
    wG.eval(`wearLog.filter(x=>x.itemId==="itm-tee-0001").length`) === 1,
    wG.eval(`JSON.stringify(wearLog)`));
  check("without disturbing what was worn yesterday",
    wG.eval(`wearLog.filter(x=>x.itemId==="itm-polo-001").length`) === 1);
  wG.eval(`openWoreSheet()`);
  check("and the sheet opens on today's outfit, not on yesterday's",
    (wG.eval(`woreDraft`) || {}).base === "itm-tee-0001",
    wG.eval(`JSON.stringify(woreDraft)`));

  /* Undo takes back the LESSON as well as the laundry. This is what somebody taps
     on realising they logged the wrong outfit, and reverting the wear log while the
     advisor went on learning the preference would leave the app believing something
     the user had just told it was not so. Raised by the pre-push reviewer,
     2026-08-29. */
  ev(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[]; swaps=[];
      trips=[]; lastRes={picks:{base:"itm-tee-0001"}}; lastPickIds=["itm-tee-0001"];
      wornLogged=false; woreDraft={base:"itm-polo-001"};`);
  await ev(`saveWore()`);
  check("the correction is recorded and the garment logged",
    ev(`swaps.length`) === 1 && ev(`activeWears("itm-polo-001")`) === 1);
  await ev(`document.getElementById("dWear").onclick()`);
  check("undo takes back the laundry", ev(`activeWears("itm-polo-001")`) === 0);
  check("and the correction with it", ev(`swaps.length`) === 0, ev(`JSON.stringify(swaps)`));

  /* Changing a slot BACK to what was suggested retracts the correction. Skipping
     straight past on equality left the old swap standing: the wear log showed the
     suggestion and the advisor went on learning the preference the user had just
     undone. Raised by the pre-push reviewer, 2026-08-29. */
  ev(`swaps=[]; wearLog=[]; lastRes={picks:{base:"itm-tee-0001"}};
      lastPickIds=["itm-tee-0001"]; wornLogged=false;
      woreDraft={base:"itm-polo-001"};`);
  await ev(`saveWore()`);
  check("the correction is recorded", ev(`swaps.length`) === 1, ev(`swaps`));
  ev(`woreDraft={base:"itm-tee-0001"};`);
  await ev(`saveWore()`);
  check("and changing back to the suggestion retracts it",
    ev(`swaps.length`) === 0, ev(`JSON.stringify(swaps)`));

  /* On a trip the advice comes from the suitcase, so a garment left at home could
     not have been part of it. The reviewer asked for those to be removed; they are
     MARKED instead — this sheet exists to record what actually happened, and
     sometimes what happened is that the packing list was wrong. Refusing to let the
     user say so would make the one screen for telling the truth the one screen that
     argues back. Marking keeps an accidental tap visible without removing the
     deliberate one. Rejected in part, 2026-08-29. */
  const dISO = (o) => { const x = new Date(Date.now() + o * 86400000);
    return `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,"0")}-${String(x.getDate()).padStart(2,"0")}`; };
  ev(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[]; swaps=[];
      trips=[{id:"t",start:"${dISO(-1)}",end:"${dISO(2)}",packed:[{id:"itm-tee-0001",qty:1}]}];
      lastRes={picks:{base:"itm-tee-0001"}}; lastOutfit={base:"white tee"};
      lastPickIds=["itm-tee-0001"]; wornLogged=false;`);
  ev(`openWoreSheet()`);
  const away = [...w.document.querySelector('[data-wore="base"]').options]
    .map(o => o.textContent);
  check("a garment left at home is still offered",
    away.some(t => /navy polo/.test(t)), away);
  check("but marked, so choosing it is deliberate",
    away.some(t => /navy polo \(not packed\)/.test(t)), away);
  check("and what IS packed comes first",
    away.indexOf("white tee (suggested)") < away.findIndex(t => /not packed/.test(t)),
    away);
  ev(`trips=[];`);

  /* A preference may only name a garment in the wardrobe being SENT.
     closetPayload() drops the laundry, and on a trip it is the suitcase — so a
     favourite left at home would have the prompt asking the model to prefer an id
     that is not in the list beneath it, and obliging would spend the one corrective
     retry on a contradiction this end put there. Raised by the pre-push reviewer,
     2026-08-29. */
  ev(`closet=[${JSON.stringify(POLO)}]; trips=[]; wearLog=[];
      swaps=[{day:"2026-08-20",slot:"base",wore:"itm-polo-001",instead:null},
             {day:"2026-08-21",slot:"base",wore:"itm-polo-001",instead:null}];`);
  check("a wearable favourite is offered",
    ev(`swapSummary(closetPayload())`).length === 1, ev(`swapSummary(closetPayload())`));
  ev(`wearLog=[{itemId:"itm-polo-001",wornAt:Date.now()},
                {itemId:"itm-polo-001",wornAt:Date.now()-1000}];`);
  check("one in the wash is not — it is not in the wardrobe being sent",
    ev(`closetPayload().length`) === 0 && ev(`swapSummary(closetPayload())`).length === 0,
    { sent: ev(`closetPayload().length`), prefers: ev(`swapSummary(closetPayload())`) });
  ev(`wearLog=[];`);

  /* The habits have to reach the 06:45 push — the advice the user mostly reads. */
  check("the worker forwards what they reach for",
    /body\.put\("prefers", prefers\)/.test(kt),
    "preferences are stored but never sent with the morning request");

  console.log("\n--- 16. one swap is a day; two is a habit ----------------------");
  ev(`swaps=[{day:"2026-08-20",slot:"base",wore:"itm-polo-001",instead:"itm-tee-0001"}];`);
  check("a single correction is not reported as a preference",
    ev(`swapSummary()`).length === 0, ev(`swapSummary()`));
  ev(`swaps.push({day:"2026-08-21",slot:"base",wore:"itm-polo-001",instead:"itm-tee-0001"});`);
  const sum2 = ev(`swapSummary()`);
  check("twice is", sum2.length === 1 && sum2[0].label === "navy polo", sum2);
  check("with the slot and the count", sum2[0].slot === "base" && sum2[0].n === 2, sum2[0]);
  /* And the ID. Two garments can share a name, and a preference naming only the
     label cannot say which was reached for — the advisor could honour it faithfully
     with the wrong item. Raised by the pre-push reviewer, 2026-08-29. */
  check("and the id, so two garments of one name stay distinct",
    sum2[0].id === "itm-polo-001", sum2[0]);

  /* A slot with no row to review must not keep a garment in the draft. One deleted
     since the advice, with nothing left that can play the role, would otherwise be
     logged invisibly on save. */
  ev(`closet=[${JSON.stringify(POLO)}]; wearLog=[]; swaps=[];
      lastRes={picks:{outer:"itm-gone-001", base:"itm-polo-001"}};
      lastOutfit={base:"navy polo"}; lastPickIds=[]; wornLogged=false;`);
  ev(`openWoreSheet()`);
  check("a slot with nothing to show holds nothing in the draft",
    ev(`woreDraft.outer`) === null, ev(`JSON.stringify(woreDraft)`));
  await ev(`saveWore()`);
  check("so nothing invisible is logged",
    ev(`activeWears("itm-gone-001")`) === 0 &&
    !ev(`swaps`).some(x => x.wore === "itm-gone-001"), ev(`JSON.stringify(swaps)`));
  ev(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)}]; wearLog=[]; swaps=[];`);

  // Old habits fade rather than standing for ever.
  ev(`swaps=[{day:"2020-01-01",slot:"base",wore:"itm-polo-001",instead:null},
             {day:"2020-01-02",slot:"base",wore:"itm-polo-001",instead:null}];`);
  check("corrections past the keep-window stop counting",
    ev(`swapSummary()`).length === 0, ev(`swapSummary()`));

  // A garment since removed from the closet cannot be a preference.
  ev(`swaps=[{day:todayISO(),slot:"base",wore:"gone-0001",instead:null},
             {day:dayISO(Date.now()-86400000),slot:"base",wore:"gone-0001",instead:null}];`);
  check("a garment no longer owned is not offered back",
    ev(`swapSummary()`).length === 0, ev(`swapSummary()`));

  console.log("\n--- 17. the advisor is told, as a preference --------------------");
  ev(`swaps=[{day:"2026-08-20",slot:"base",wore:"itm-polo-001",instead:"itm-tee-0001"},
             {day:"2026-08-21",slot:"base",wore:"itm-polo-001",instead:"itm-tee-0001"}];
      __sent=null;
      fetch = async (u,o) => { __sent=JSON.parse(o.body);
        return {ok:true, json: async () => ({weather:${JSON.stringify(WX)},
          outfit:{base:"navy polo"}, outfit_text:"x", source:"llm"})}; };`);
  await ev(`getAdvice(40.3,-74.6)`);
  check("the request carries what they reach for",
    (ev(`__sent.prefers`) || []).length === 1 && ev(`__sent.prefers[0].label`) === "navy polo",
    ev(`__sent.prefers`));
  await ev(`savePushPayload()`);
  check("and the morning push is told too",
    (JSON.parse(w.localStorage.getItem("oa.pushPayload")).prefers || []).length === 1);

  // Choosing differently says nothing about what the wardrobe LACKS.
  ev(`gaps=[];`);
  check("a correction is never mistaken for a wardrobe gap", ev(`gaps.length`) === 0);

  console.log("\n--- 18. the pictures show TODAY'S outfit (2026-08-30) -----------");
  /* User: "once I picked I wore something else, replace the pictures to show the
     accurate TODAY'S OUTFIT." The card is the answer to "what am I wearing today",
     and after a correction the suggestion is no longer that answer. */
  const COAT18 = {id:"itm-coat-001", label:"grey overcoat", category:"outer",
    group:"outerwear", type:"coat", roles:["outer"], colors:[], warmth:4,
    formality:["smart"], waterproof:false, count:1};
  const grid = (win) => [...win.document.querySelectorAll("#wearGrid .wearIt")]
    .map(t => ({ slot: t.dataset.slot, pick: t.dataset.pick,
                 name: t.querySelector(".nm2").textContent }));
  const listVal = (win, slot) => {
    const el = win.document.querySelector(`#outfitList li[data-slot="${slot}"] .val`);
    return el ? el.textContent : null;
  };
  const wV = page();
  await wV.eval("appReady");
  const ADVICE = { base: "white tee", outer: "a light waterproof shell",
                   bottoms: "chinos" };
  const RES_V = { closetUsed: true, picks: { base: "itm-tee-0001" },
                  weather: WX, outfit: ADVICE, text: "wear the tee" };
  wV.eval(`closet=[${JSON.stringify(WTEE)},${JSON.stringify(POLO)},${JSON.stringify(COAT18)}];
           wearLog=[]; swaps=[]; trips=[]; woreLogged=null; wornLogged=false;
           lastWeather=${JSON.stringify(WX)}; lastText="wear the tee"; lastSource="llm";
           lastOutfit=${JSON.stringify(ADVICE)}; lastRes=${JSON.stringify(RES_V)};`);
  wV.eval(`renderOutfit(lastOutfit,lastText,lastSource,lastRes)`);
  check("before any correction the pictures are the suggestion",
    (grid(wV).find(t => t.slot === "base") || {}).name === "white tee",
    grid(wV));
  check("and nothing announces a correction that has not happened",
    wV.document.getElementById("wornNote").style.display === "none");

  /* The correction itself. */
  wV.eval(`woreDraft={base:"itm-polo-001"};`);
  await wV.eval(`saveWore()`);
  const g1 = grid(wV);
  check("the picture is now of what was actually worn",
    (g1.find(t => t.slot === "base") || {}).name === "navy polo" &&
    (g1.find(t => t.slot === "base") || {}).pick === "itm-polo-001", g1);
  check("the item-by-item list agrees with the picture",
    listVal(wV, "base") === "navy polo", listVal(wV, "base"));
  check("and the card says whose outfit it is showing",
    wV.document.getElementById("wornNote").style.display !== "none" &&
    /actually wore/.test(wV.document.getElementById("wornNoteTxt").textContent),
    wV.document.getElementById("wornNoteTxt").textContent);

  /* The advisor suggested a shell they do not own. The record speaks only about the
     closet, so its silence there is not a denial — that line has to stand. */
  check("a suggestion they do not own is left alone",
    (g1.find(t => t.slot === "outer") || {}).name === "a light waterproof shell", g1);
  check("and so is a generic slot the closet never filled",
    (g1.find(t => t.slot === "bottoms") || {}).name === "chinos", g1);

  /* The suggestion must stay reachable — "Why this", read under pictures of
     something else, is the reasoning for the outfit that was NOT worn. */
  wV.eval(`document.getElementById("wornToggle").onclick()`);
  check("one tap goes back to what was suggested",
    (grid(wV).find(t => t.slot === "base") || {}).name === "white tee",
    grid(wV));
  check("and the banner offers the way back",
    /wore something else/.test(wV.document.getElementById("wornNoteTxt").textContent) &&
    /Show what I wore/.test(wV.document.getElementById("wornToggle").textContent),
    wV.document.getElementById("wornToggle").textContent);
  wV.eval(`document.getElementById("wornToggle").onclick()`);
  check("and back again", (grid(wV).find(t => t.slot === "base") || {}).name === "navy polo");

  /* "I wore nothing there" is an answer too — but only where the advice named one
     of THEIR garments, which is the only kind of slot the sheet asks about. */
  wV.eval(`woreDraft={base:null};`);
  await wV.eval(`saveWore()`);
  check("a slot they say they left empty loses its picture",
    !grid(wV).some(t => t.slot === "base"), grid(wV));
  check("and the list says so rather than going blank",
    listVal(wV, "base") === "None worn", listVal(wV, "base"));

  /* Undo puts the suggestion back: there is no longer a record to show instead. */
  wV.eval(`woreDraft={base:"itm-polo-001"};`);
  await wV.eval(`saveWore()`);
  await wV.eval(`document.getElementById("dWear").onclick()`);
  check("undoing the record returns the card to the advice",
    (grid(wV).find(t => t.slot === "base") || {}).name === "white tee", grid(wV));
  check("and the banner goes with it",
    wV.document.getElementById("wornNote").style.display === "none");

  /* "Wearing it" records the suggestion. Nothing was corrected, so nothing is
     announced — a banner on every logged outfit is noise. */
  await wV.eval(`document.getElementById("dWear").onclick()`);
  check("confirming the suggestion announces no correction",
    wV.eval(`woreLogged !== null`) &&
    wV.document.getElementById("wornNote").style.display === "none",
    wV.eval(`JSON.stringify(woreLogged)`));

  /* Later the same day, fresh advice is a fresh answer — the morning's record does
     not overwrite the suggestion the user just asked for. It is still kept, and one
     tap still shows it. */
  await wV.eval(`document.getElementById("dWear").onclick()`);   // undo
  wV.eval(`woreDraft={base:"itm-polo-001"};`);
  await wV.eval(`saveWore()`);
  wV.eval(`lastOutfit={base:"white tee"}; lastText="x"; lastSource="llm";
           lastRes={closetUsed:true,picks:{base:"itm-tee-0001"},weather:lastWeather,
                    outfit:lastOutfit,text:"x"};
           renderOutfit(lastOutfit,lastText,lastSource,lastRes)`);
  check("new advice shows the new suggestion, not this morning's clothes",
    (grid(wV).find(t => t.slot === "base") || {}).name === "white tee", grid(wV));
  check("while the record it does not overwrite is still there to show",
    wV.document.getElementById("wornNote").style.display !== "none" &&
    (wV.eval(`woreLogged`) || {}).base === "itm-polo-001",
    wV.eval(`JSON.stringify(woreLogged)`));
  check("and this morning's clothes are still in the laundry",
    wV.eval(`activeWears("itm-polo-001")`) === 1);

  /* A relaunch has to come back to what was worn without a tap. loadToday draws the
     advice before the record is readable, so the card is redrawn once it is. */
  await wV.eval(`saveToday(lastRes,"app")`);
  const carriedV = {};
  for (const k of ["oa.woreToday", "oa.closet", "oa.wearlog", "oa.swaps", "oa.today"])
    if (wV.localStorage.getItem(k) != null) carriedV[k] = wV.localStorage.getItem(k);
  const wW = page();
  for (const k in carriedV) wW.localStorage.setItem(k, carriedV[k]);
  await wW.eval("appReady");
  check("a relaunch shows what was worn, not what was advised",
    (grid(wW).find(t => t.slot === "base") || {}).name === "navy polo", grid(wW));
  check("with the banner explaining why",
    wW.document.getElementById("wornNote").style.display !== "none" &&
    /actually wore/.test(wW.document.getElementById("wornNoteTxt").textContent),
    wW.document.getElementById("wornNoteTxt").textContent);

  /* Renaming the garment on the card. The worn view shows the CLOSET's label, so
     an edit that never reached the card left it captioned with the old name. */
  await wW.eval(`openSheet(closet.find(i=>i.id==="itm-polo-001"),{isNew:false})`);
  wW.document.getElementById("shLabel").value = "navy piqué polo";
  await wW.eval(`document.getElementById("shSave").onclick()`);
  check("renaming the garment renames it on the card",
    (grid(wW).find(t => t.slot === "base") || {}).name === "navy piqué polo",
    grid(wW));

  /* A garment deleted after it was logged. Its wears are cascaded away with it, so
     there is no name and no photo left — and putting the SUGGESTION back in that
     slot would show a garment they said they did not wear. */
  /* Driven through the delete BUTTON, not by calling the redraw: every write to
     the closet goes through saveCloset, and that is where the card is kept honest.
     Raised by the pre-push reviewer, 2026-08-30 — the first version of this test
     called refreshOutfitView() itself and so proved only that the overlay worked,
     not that anything would ever run it. */
  await wW.eval(`openSheet(closet.find(i=>i.id==="itm-polo-001"),{isNew:false})`);
  await wW.eval(`document.getElementById("shDel").onclick()`);
  check("deleting the garment is enough to redraw the card",
    !wW.eval(`closet.some(i=>i.id==="itm-polo-001")`), wW.eval(`closet.length`));
  check("a deleted garment does not hand the slot back to the suggestion",
    !grid(wW).some(t => t.name === "white tee"), grid(wW));
  check("the slot says it cannot be shown",
    /no longer in your closet/.test(listVal(wW, "base") || ""), listVal(wW, "base"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
