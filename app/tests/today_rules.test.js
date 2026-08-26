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

  w.document.querySelector("#genderSeg button").click();
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

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
