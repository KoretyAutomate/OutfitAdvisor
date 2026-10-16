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
// The notification's "Wearing it", as FeedbackReceiver writes it since 2026-10-11:
// its OWN queue (oa.nativeWears, appended) and day record (oa.nativeWore) — never the
// app's keys. One writer per key.
let natSeq = 0;
const notify = (ls, entries, record) => {
  const q = JSON.parse(ls.getItem("oa.nativeWears") || "[]");
  for (const e of entries) q.push({...e, key: `n${++natSeq}-${e.itemId}`});
  ls.setItem("oa.nativeWears", JSON.stringify(q));
  if (record) ls.setItem("oa.nativeWore", JSON.stringify(record));
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

  console.log("\n--- review round 2: clamp, reset ordering, reload race -----------");
  {
    const w = page();
    const d = w.document, ev = c => w.eval(c), ls = w.localStorage;
    await ev("appReady");
    const tap = async r => { d.querySelector(`#fbRow button[data-r="${r}"]`).click(); await ev("fbChain"); };
    // Near the clamp, replacing a rating restores where it started.
    ls.setItem("oa.feedback", "[]"); ls.setItem("oa.tempOffset", "5.7");
    await tap(2);
    check("too warm at +5.70 clamps to +6", ev("tempOffset") === 6, ev("tempOffset"));
    await tap(0);
    check("replacing it with just right goes back to +5.70, not +5.25",
      ev("tempOffset") === 5.7, ev("tempOffset"));
    check("the entry records where it started", ev("feedback[0].from") === 5.7, ev("JSON.stringify(feedback)"));

    // A reset tapped while a rating is queued comes after it.
    ls.setItem("oa.feedback", "[]"); ls.setItem("oa.tempOffset", "0");
    d.querySelector('#fbRow button[data-r="2"]').click();
    // fbNote's guard reads feedback before the rating lands; seed one so it acts.
    ev("feedback=[{at:1,rating:2}]");
    d.getElementById("fbNote").click();
    await ev("fbChain");
    check("a reset after a queued rating wins", ev("tempOffset") === 0 && ev("feedback.length") === 0 &&
      ls.getItem("oa.tempOffset") === "0", { off: ev("tempOffset"), fb: ev("JSON.stringify(feedback)") });

    // A wear logged while the foreground reload is reading is not overwritten.
    ls.setItem("oa.wearlog", "[]"); ls.setItem("oa.woreToday", "");
    ev(`wearLog=[]; woreLogged=null; woreDay=null;
        window.__pg=prefGet; prefGet=async(k,dflt)=>{ await new Promise(r=>setTimeout(r,15)); return window.__pg(k,dflt); };`);
    d.dispatchEvent(new w.Event("visibilitychange"));
    await new Promise(r => setTimeout(r, 5));
    ev(`logWear("tee1"); woreLogged={base:"tee1"}; woreDay=todayISO();`);
    for (let i = 0; i < 100 && ev("sharedBusy"); i++) await new Promise(r => setTimeout(r, 10));
    ev("prefGet=window.__pg;");
    check("the reload does not overwrite a wear made while it was reading",
      ev("wearLog.length") === 1 && ev("JSON.stringify(woreLogged)") === '{"base":"tee1"}',
      { wl: ev("JSON.stringify(wearLog)"), rec: ev("JSON.stringify(woreLogged)") });
  }

  console.log("\n--- review round 3: a closet write keeps the notification's wears --");
  {
    const w = page();
    const ev = c => w.eval(c), ls = w.localStorage;
    await ev("appReady");
    const today = ev("todayISO()");
    ev(`closet=[{id:"tee1",label:"Navy tee",category:"base",roles:["base"],count:2},
               {id:"jean1",label:"Jeans",category:"bottoms",roles:["bottoms"],count:2}];
        wearLog=[]; woreLogged=null; woreDay=null;`);
    await ev("saveCloset()");               // the page's baseline: an empty wear log
    // The notification logs tee1 while the page is in memory and has not re-read.
    const t = Date.now() - 1000;
    notify(ls, [{itemId: "tee1", wornAt: t}], {day: today, map: {base: "tee1"}});
    // The user logs jeans from the item sheet: memory changes, then saveCloset.
    ev(`logWear("jean1")`);
    await ev("saveCloset()");
    const disk = JSON.parse(ls.getItem("oa.wearlog")).map(x => x.itemId).sort();
    check("the notification's wear survives a closet write from a stale page",
      JSON.stringify(disk) === '["jean1","tee1"]', disk);
    check("and its day record is adopted", ev("JSON.stringify(woreLogged)") === '{"base":"tee1"}',
      ev("JSON.stringify(woreLogged)"));
    // A garment the page has itself logged today is not counted twice.
    notify(ls, [{itemId: "jean1", wornAt: Date.now() - 500}]);
    await ev("saveCloset()");
    check("one wear per garment per day across both writers",
      JSON.parse(ls.getItem("oa.wearlog")).filter(x => x.itemId === "jean1").length === 1,
      ls.getItem("oa.wearlog"));
    // What the page removed itself stays removed.
    ev(`unlogWearToday("jean1")`);
    await ev("saveCloset()");
    check("a wear the page took back is not merged back in",
      !JSON.parse(ls.getItem("oa.wearlog")).some(x => x.itemId === "jean1"), ls.getItem("oa.wearlog"));
  }

  console.log("\n--- review round 4: a correction takes back the notification's outfit");
  {
    const w = page();
    const d = w.document, ev = c => w.eval(c), ls = w.localStorage;
    await ev("appReady");
    const today = ev("todayISO()");
    ev(`closet=[{id:"teeA",label:"Tee A",category:"base",roles:["base"],count:1},
               {id:"teeB",label:"Tee B",category:"base",roles:["base"],count:1},
               {id:"jean1",label:"Jeans",category:"bottoms",roles:["bottoms"],count:1}];
        wearLog=[]; woreLogged=null; woreDay=null; swaps=[];
        lastRes={picks:{base:"teeA",bottoms:"jean1"},closetUsed:true,weather:${JSON.stringify(WX)}};
        lastPickIds=["teeA","jean1"]; wornLogged=false;`);
    await ev("saveCloset()");               // baseline: nothing worn
    // The notification logs outfit A; the page has not re-read.
    const t = Date.now() - 1000;
    notify(ls, [{itemId: "teeA", wornAt: t}, {itemId: "jean1", wornAt: t}], {day: today, map: {base: "teeA", bottoms: "jean1"}});
    // The user corrects to B through the sheet.
    ev(`woreDraft={base:"teeB",bottoms:"jean1"};`);
    await ev("saveWore()");
    const ids = JSON.parse(ls.getItem("oa.wearlog")).map(x => x.itemId).sort();
    check("correcting a notification-logged outfit leaves only the corrected one in the laundry",
      JSON.stringify(ids) === '["jean1","teeB"]', ids);
    check("and the record is the correction", ev("JSON.stringify(woreLogged)") === '{"base":"teeB","bottoms":"jean1"}',
      ev("JSON.stringify(woreLogged)"));
    // Undo from the button releases everything.
    ev("syncWearBtn()");
    d.getElementById("dWear").click();
    for (let i = 0; i < 30 && ev("woreBusy"); i++) await new Promise(r => setTimeout(r, 10));
    await drain();
    check("undo afterwards leaves nothing stranded", JSON.parse(ls.getItem("oa.wearlog")).length === 0,
      ls.getItem("oa.wearlog"));
    // Undo directly after a notification log, with the page still stale and its
    // button showing the record (wornLogged) from an earlier read.
    ev(`wearLog=[]; woreLogged=null; woreDay=null;`);
    await ev("saveCloset()");
    ls.removeItem("oa.nativeWears"); ev("nativeSeen=new Set()");
    notify(ls, [{itemId: "teeA", wornAt: t}], {day: today, map: {base: "teeA"}});
    ev(`woreLogged={base:"teeA"}; woreDay=todayISO(); wornLogged=true;`);
    d.getElementById("dWear").click();
    for (let i = 0; i < 30 && ev("woreBusy"); i++) await new Promise(r => setTimeout(r, 10));
    await drain();
    check("undo releases a wear only the disk knew about", JSON.parse(ls.getItem("oa.wearlog")).length === 0,
      ls.getItem("oa.wearlog"));
  }

  console.log("\n--- review round 5: the day record is synced on its own ----------");
  {
    const w = page();
    const ev = c => w.eval(c), ls = w.localStorage;
    await ev("appReady");
    const today = ev("todayISO()");
    const setup = () => ev(`closet=[{id:"teeA",label:"Tee A",category:"base",roles:["base"],count:1},
               {id:"teeB",label:"Tee B",category:"base",roles:["base"],count:1},
               {id:"jean1",label:"Jeans",category:"bottoms",roles:["bottoms"],count:1}];
        swaps=[]; lastRes={picks:{base:"teeA",bottoms:"jean1"},closetUsed:true,weather:${JSON.stringify(WX)}};
        lastPickIds=["teeA","jean1"]; wornLogged=false;`);
    // (a) The page still holds YESTERDAY's record when the notification logs today.
    setup();
    ev(`wearLog=[]; woreLogged=null; woreDay=null;`);
    await ev("saveCloset()");
    ev(`woreLogged={base:"teeB"}; woreDay="2000-01-01";`);
    const t = Date.now() - 1000;
    notify(ls, [{itemId: "teeA", wornAt: t}, {itemId: "jean1", wornAt: t}], {day: today, map: {base: "teeA", bottoms: "jean1"}});
    ev(`woreDraft={base:"teeB",bottoms:"jean1"};`);
    await ev("saveWore()");
    let ids = JSON.parse(ls.getItem("oa.wearlog")).map(x => x.itemId).sort();
    check("a stale page's old record does not erase the notification's, and the correction releases A",
      JSON.stringify(ids) === '["jean1","teeB"]', ids);
    // (b) The notification writes the record with the wear log unchanged — a fresh
    // start, so the page has not adopted any receiver record yet.
    setup();
    ls.setItem("oa.woreToday", ""); ls.removeItem("oa.nativeWoreSeen"); ev(`nativeWoreSeen=""`);
    ev(`wearLog=[]; logWear("teeA"); logWear("jean1"); woreLogged=null; woreDay=null;`);
    await ev("saveCloset()");               // both on disk, logged from their sheets
    notify(ls, [], {day: today, map: {base: "teeA", bottoms: "jean1"}});
    ev(`woreDraft={base:"teeB",bottoms:"jean1"};`);
    await ev("saveWore()");
    ids = JSON.parse(ls.getItem("oa.wearlog")).map(x => x.itemId).sort();
    check("a record written without a wear-log change is still learned before a correction",
      JSON.stringify(ids) === '["jean1","teeB"]', ids);
    // Reading the record never writes over the disk.
    ls.setItem("oa.woreToday", JSON.stringify({day: today, map: {base: "teeA"}}));
    ev(`woreLogged={base:"teeB"}; woreDay="2000-01-01"; wearRecord();`);
    await drain();
    check("expiring yesterday's record in memory leaves the disk alone",
      JSON.parse(ls.getItem("oa.woreToday")).map.base === "teeA", ls.getItem("oa.woreToday"));
  }

  console.log("\n--- FeedbackReceiver.kt mirrors one-rating-a-day ------------------");
  {
    const kt = KT("FeedbackReceiver.kt");
    check("it finds today's entry by local calendar day",
      /dayOf\(e\.optLong\("at", 0L\)\) == today/.test(kt) && /SimpleDateFormat\("yyyy-MM-dd"/.test(kt));
    check("reverts its step before applying the new one (twin of fbRevert)",
      /clamp\(round2\(current - RATE \* \(DELTA\[/.test(kt) &&
      kt.indexOf("current - RATE * (DELTA[") < kt.indexOf("current + RATE * delta"));
    check("and drops it, so the day keeps one entry", /log\.remove\(prevIdx\)/.test(kt));
    check("the new entry uses the same clock as the day test", /put\("at", now\)/.test(kt));
    check("it records the offset a rating started from, as the app does",
      /\.put\("from", round2\(current\)\)/.test(kt) && /feedback\.push\(\{at:(Date\.now\(\)|tapAt),rating,from\}\)/.test(SRC));   // tapAt: stamped at the tap (2026-10-16)
    check("and replaces by restoring it, falling back to the step for old entries",
      /optDouble\("from", Double\.NaN\)/.test(kt) && /if \(!from\.isNaN\(\)\) clamp\(from\)/.test(kt));
  }

  console.log("\n--- 'Wearing it' from the notification ---------------------------");
  {
    const fb = KT("FeedbackReceiver.kt"), note = KT("OutfitNotification.kt"),
          worker = KT("AdviceWorker.kt");
    const manifest = fs.readFileSync(path.join(__dirname, "..", "android", "app", "src", "main",
      "AndroidManifest.xml"), "utf8");
    const kconst = name => (fb.match(new RegExp(`const val ${name} = "([^"]+)"`)) || [])[1];
    // One writer per key (2026-10-11): the receiver writes ONLY its own queue and day
    // record, which the app reads; never the app's wear log, record or snapshot.
    const onWear = fb.slice(fb.indexOf("private fun onWear"), fb.indexOf("private fun loggedToday"));
    check("the receiver writes only its own keys, which the app reads",
      kconst("KEY_NATIVE_WEARS") === "oa.nativeWears" && /prefGet\("oa\.nativeWears"/.test(SRC) &&
      kconst("KEY_NATIVE_WORE") === "oa.nativeWore" && /prefGet\("oa\.nativeWore"/.test(SRC) &&
      !/putString\(KEY_WEARLOG|putString\(KEY_WORE\b|KEY_PUSH_PAYLOAD/.test(onWear), onWear.slice(-300));
    check("and still knows the app's day-record key, to stay idempotent",
      kconst("KEY_WORE") === (SRC.match(/const WORE_KEY="([^"]+)"/) || [])[1], kconst("KEY_WORE"));
    check("an unwashed wear is held as long as the app holds it",
      +(fb.match(/COOLDOWN_DAYS = (\d+)/) || [])[1] === +(SRC.match(/COOLDOWN_DAYS=(\d+)/) || [])[1]);
    check("wear entries have the app's fields",
      /put\("itemId", id\)\.put\("wornAt", now\)\.put\("key"/.test(fb) && /wearLog\.push\(\{itemId:e\.itemId,wornAt:e\.wornAt\}\)/.test(SRC));
    check("the day record has the app's fields",
      /put\("day", today\)\.put\("map", picks\)/.test(fb) && /JSON\.stringify\(\{day:woreDay, map:woreLogged\}\)/.test(SRC));
    check("one wear per garment per day, like logWear",
      /e\.optString\("itemId"\) == id && dayOf\(e\.optLong\("wornAt", 0L\)\) == today/.test(fb));
    check("idempotent: an existing record for today means nothing is written",
      fb.indexOf("if (loggedToday(prefs, today))") < fb.indexOf("putString(KEY_NATIVE_WEARS"));
    check("a tap on another day's notification logs nothing",
      /intent\.getStringExtra\(EXTRA_DAY\) != today/.test(fb));
    check("null slots are not logged as a garment called \"null\"",
      /v is String && v\.isNotEmpty\(\)/.test(fb));
    check("the WEAR action is routed and registered",
      /intent\.action == ACTION_WEAR/.test(fb) &&
      manifest.includes('<action android:name="com.korety.outfitadvisor.WEAR" />') &&
      kconst("ACTION_WEAR") === "com.korety.outfitadvisor.WEAR");
    const post = note.slice(note.indexOf("fun post("), note.indexOf("fun postUpdate("));
    const withWear = post.slice(post.indexOf("if (wearPicks != null"), post.indexOf("} else {"));
    check("with picks: Wearing it, Too cold, Too warm — three actions, Android's limit",
      (withWear.match(/addAction\(/g) || []).length === 3 &&
      withWear.indexOf("wearAction") < withWear.indexOf("Too cold") &&
      withWear.indexOf("Too cold") < withWear.indexOf("Too warm") && !/Just right/.test(withWear), withWear);
    check("without picks: the three verdicts as before", /b\.setActions\(\*ratingActions\(context\)\)/.test(post));
    check("the push offers it only for closet advice (the app's rule)",
      /wearPicks = advice\.raw\?\.takeIf \{ it\.optBoolean\("closetUsed", false\) \}/.test(worker) &&
      /res&&res\.closetUsed&&res\.picks/.test(SRC));
    // Raised by the pre-push reviewer, 2026-10-11: the snapshot hold must count
    // only NEW wears, and must see a unit that came back from `pending`.
    check("the worker holds only queue wears the snapshot has not folded in",
      /e\.optString\("key"\) in seen/.test(fb) && /FeedbackReceiver\.applyNativeWears\(/.test(worker) &&
      /nativeSeen:\[\.\.\.nativeSeen\]/.test(SRC));
    const hold = fb.slice(fb.indexOf("fun applyNativeWears"), fb.indexOf("fun applyNativeWears") + 3000);
    check("the hold reads both snapshot arrays, as freedBy does",
      /listOfNotNull\(p\.optJSONArray\("closet"\), p\.optJSONArray\("pending"\)\)/.test(hold) &&
      /listOfNotNull\(closet, pending\)/.test(worker));
    check("and counts units already back before taking one",
      /if \(t <= now\) n\+\+ else still\.put\(t\)/.test(hold) &&
      hold.indexOf("n++") < hold.indexOf("if (n < 1) continue") &&
      hold.indexOf("if (n < 1) continue") < hold.indexOf('o.put("availableCount", n - 1)'));
    check("request code 4794 is not shared", (fb + note + worker).split("= 4794").length === 2 && !/= 4794/.test(note + worker));

    // The app reading what the receiver writes, as the button would have written it.
    const w = page();
    const d = w.document, ev = c => w.eval(c), ls = w.localStorage;
    await ev("appReady");
    const today = ev("todayISO()");
    ev(`closet=[{id:"tee1",label:"Navy tee",category:"base",roles:["base"],count:2},
               {id:"jean1",label:"Jeans",category:"bottoms",roles:["bottoms"],count:1}];
        wearLog=[]; woreLogged=null; woreDay=null;
        lastRes={picks:{base:"tee1",bottoms:"jean1",outer:null},closetUsed:true,weather:${JSON.stringify(WX)}};
        lastPickIds=["tee1","jean1"]; wornLogged=false; syncWearBtn();`);
    // Exactly what onWear writes:
    const now = Date.now();
    ls.setItem("oa.wearlog", JSON.stringify([{itemId: "tee1", wornAt: now}, {itemId: "jean1", wornAt: now}]));
    ls.setItem("oa.woreToday", JSON.stringify({day: today, map: {base: "tee1", bottoms: "jean1", outer: null}}));
    // App is still open with stale memory; the user taps the in-app button too.
    d.getElementById("dWear").click();
    for (let i = 0; i < 30 && ev("woreBusy"); i++) await new Promise(r => setTimeout(r, 10));
    await drain();
    check("the in-app button adopts the notification's log instead of logging again",
      ev("wearLog.length") === 2, ev("JSON.stringify(wearLog)"));
    check("the record is today's, from the notification",
      ev("JSON.stringify(woreLogged)") === '{"base":"tee1","bottoms":"jean1","outer":null}');
    check("the button now offers undo", /Logged/.test(d.getElementById("dWear").textContent),
      d.getElementById("dWear").textContent);
    check("and the garments read as worn", ev(`avail(closet[0])`) === 1 && ev(`avail(closet[1])`) === 0,
      [ev(`avail(closet[0])`), ev(`avail(closet[1])`)]);
    // Undo works on a notification-written record like on the app's own.
    d.getElementById("dWear").click();
    for (let i = 0; i < 30 && ev("woreBusy"); i++) await new Promise(r => setTimeout(r, 10));
    await drain();
    check("undo releases what the notification logged", ev("wearLog.length") === 0 && ev("woreLogged") === null,
      ev("JSON.stringify(wearLog)"));
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
