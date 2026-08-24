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

  // The worker must read the very key the app writes, and refuse a stale copy.
  const jsPush = (fs.readFileSync(HTML, "utf8").match(/const PUSH_PAYLOAD_KEY="([^"]+)"/) || [])[1];
  const ktPush = (kt.match(/const val KEY_PUSH_PAYLOAD = "([^"]+)"/) || [])[1];
  check("the phone and the worker agree on the payload key",
    jsPush === ktPush, { jsPush, ktPush });
  check("the worker attaches it to the morning request",
    /body\.put\("closet", closet\)/.test(kt) && /body\.put\("rules", rules\)/.test(kt));
  check("and refuses one too old to describe the wardrobe",
    /PUSH_PAYLOAD_MAX_AGE_MS/.test(kt) && /age !in 0\.\./.test(kt));

  console.log("\n--- 8. removing a rule --------------------------------------------");
  ev(`userRules=[{id:"a",kind:"avoid_pair",a:{type:"jeans"},b:{type:"blazer"},
                  restated:"No jeans with a blazer",text:"x"}]; renderRules();`);
  w.document.querySelector('[data-rlrm="0"]').click();
  await new Promise(r => setTimeout(r, 20));
  check("it goes", ev(`userRules.length`) === 0, ev(`userRules`));
  check("and the list says so rather than sitting empty",
    /Nothing banned yet/.test(w.document.getElementById("rlList").textContent));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
