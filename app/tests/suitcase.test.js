/**
 * suitcase.test.js — on a trip, the advice comes from what is with you
 * (user, 2026-09-10, from Tokyo: "it should only pick from the packed items … tried
 * adding packed items, but some received error").
 *
 * The suitcase used to be set only by the "Packed it" button under a SERVER packing
 * list, and once away the server refused the list ("already started") while the
 * trip sheet refused the trip. Pinned here:
 *   - the packing sheet is a CHECKLIST: the server's items ticked, the rest of the
 *     wardrobe under "Also with me" unticked, and Packed it saves the ticks;
 *   - with the suitcase declared, closetPayload() answers with it alone;
 *   - the checklist is drawn even when the server cannot be reached;
 *   - a 4xx shows the server's own sentence, not "couldn't reach";
 *   - a trip under way can still be saved in the trip sheet; a finished one cannot;
 *   - the advice card says when a trip covers today and no suitcase is declared.
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * Run: npm test   (or: node tests/suitcase.test.js)
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
const page = () => new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
}).window;
const drain = () => new Promise(r => setTimeout(r, 0));
const day = n => { const d = new Date(Date.now() + n * 86400000);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; };

const item = (id, label, cat, count = 1) => ({id, label, category: cat, group: cat === "bottoms" ? "bottoms" : "tops",
  type: cat === "bottoms" ? "chinos" : "t_shirt", roles: [cat], colors: ["navy"], warmth: 2, formality: ["casual"],
  waterproof: false, count, dirty: 0, photo: false});
const CLOSET = [item("t1", "navy tee", "base", 2), item("t2", "white tee", "base", 4), item("b1", "chinos", "bottoms")];
const TRIP = {id: "trip1", place: "Tokyo, Japan", start: day(-2), end: day(4), type: "business",
  lat: 35.68, lon: 139.77, styles: ["casual"], packed: [], notifyDays: 2};
const DAYS = [0, 1, 2].map(i => ({date: day(i), lo: 19, hi: 22, desc: "Cloudy", rain: 20, wind: 3, code: 3, emoji: "☁️"}));
const REPLY = {
  trip: {nDays: 5, forecastDays: 5, type: "business", styles: ["casual"], truncated: false, started: true},
  forecast: {mode: "forecast", days: DAYS, summary: {mode: "forecast", nDays: 5, loMin: 19, hiMax: 22, rainDays: 0, isSnow: false}},
  pack: [{id: "t1", category: "base", label: "navy tee", qty: 2, why: "a"}, {id: "b1", category: "bottoms", label: "chinos", qty: 1, why: "b"}],
  gaps: [], packing_text: "• Tops: tees", closetUsed: true, travel: false, plan: [],
};
const OUTFIT = {inner: "", base: "navy tee", mid: "", outer: "", bottoms: "chinos", footwear: "", accessories: "", tip: "x"};

(async () => {
  console.log("\n--- 1. the packing sheet is a checklist ------------------------------");
  const w = page();
  await w.eval("appReady");
  await w.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  await w.eval(`trips=[${JSON.stringify(TRIP)}]; saveTrips()`);
  w.fetch = async (url, opts) => String(url).endsWith("/packing")
    ? {ok: true, status: 200, json: async () => REPLY} : {ok: true, status: 200, json: async () => ({})};
  await w.eval(`openPacking(trips[0])`);
  await drain(); await drain();
  const doc = w.document;
  const listed = [...doc.querySelectorAll("#pkList .pkChk")];
  const more = [...doc.querySelectorAll("#pkMore .pkChk")];
  check("the server's items come ticked", listed.length === 2 && listed.every(c => c.checked), listed.map(c => c.dataset.id));
  check("the rest of the wardrobe waits unticked under Also with me",
    more.length === 1 && more[0].dataset.id === "t2" && !more[0].checked && /Also with me/.test(doc.getElementById("pkMore").textContent));
  check("the button offers to pack", doc.getElementById("pkPacked").style.display !== "none"
    && /Packed it/.test(doc.getElementById("pkPacked").textContent));

  console.log("\n--- 2. Packed it saves the ticks, and the advice follows them ---------");
  const t2box = doc.querySelector('#pkMore .pkChk[data-id="t2"]').closest("label").querySelector(".pkQty");
  check("a multiple offers a number, defaulting to ONE, not to all you own", !!t2box && t2box.value === "1" && t2box.max === "4", t2box && t2box.value);
  more[0].checked = true;                       // I did bring the white tee…
  t2box.value = "2";                            // …two of the four
  listed.find(c => c.dataset.id === "b1").checked = false;   // the chinos stayed home
  doc.getElementById("pkPacked").onclick();
  await drain(); await drain();
  const packed = JSON.parse(w.eval("JSON.stringify(trips[0].packed)"));
  check("packed is exactly what was ticked, with the quantities chosen",
    JSON.stringify(packed.map(p => p.id).sort()) === '["t1","t2"]' && packed.find(p => p.id === "t1").qty === 2
    && packed.find(p => p.id === "t2").qty === 2, packed);
  check("and the moment is stamped", w.eval("typeof trips[0].packedAt") === "number");
  check("the trip is now under way in the app's eyes", w.eval("!!tripInProgress()"));
  const payload = JSON.parse(w.eval("JSON.stringify(closetPayload())"));
  check("and the advice would be drawn from the suitcase alone",
    payload.length === 2 && payload.every(i => ["t1", "t2"].includes(i.id)), payload.map(i => i.id));
  check("the sheet closed", !doc.getElementById("packWrap").classList.contains("show"));

  console.log("\n--- 3. reopening shows the declared suitcase, not the server's list ---");
  await w.eval(`openPacking(trips[0])`);
  await drain(); await drain();
  const again = Object.fromEntries([...doc.querySelectorAll("#packWrap .pkChk")].map(c => [c.dataset.id, c.checked]));
  check("ticks reflect what was declared", again.t1 === true && again.t2 === true && again.b1 === false, again);
  check("the button now says update", /Update what's in my suitcase/.test(doc.getElementById("pkPacked").textContent));

  console.log("\n--- 4. without the server, the suitcase is still yours to declare ------");
  const w2 = page();
  await w2.eval("appReady");
  await w2.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  await w2.eval(`trips=[${JSON.stringify(TRIP)}]; saveTrips()`);
  w2.fetch = async () => { throw new TypeError("Failed to fetch"); };
  await w2.eval(`openPacking(trips[0])`);
  await drain(); await drain();
  const off = [...w2.document.querySelectorAll("#pkMore .pkChk")];
  check("every owned item is offered, unticked", off.length === 3 && off.every(c => !c.checked), off.length);
  check("and the connection error is still shown", /Couldn't reach/.test(w2.document.getElementById("pkErr").textContent));
  off[0].checked = true;
  w2.document.getElementById("pkPacked").onclick();
  await drain(); await drain();
  check("Packed it works offline", w2.eval("trips[0].packed.length") === 1);

  console.log("\n--- 4b. an answer of the wrong shape still leaves the checklist ---------");
  const w2b = page();
  await w2b.eval("appReady");
  await w2b.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  await w2b.eval(`trips=[${JSON.stringify(TRIP)}]; saveTrips()`);
  w2b.fetch = async () => ({ok: true, status: 200, json: async () => ({})});
  await w2b.eval(`openPacking(trips[0])`);
  await drain(); await drain();
  check("the error is shown", /couldn't be read/.test(w2b.document.getElementById("pkErr").textContent));
  check("and the wardrobe checklist is still there to tick",
    w2b.document.querySelectorAll("#pkMore .pkChk").length === 3 && w2b.document.getElementById("pkPacked").style.display !== "none");

  console.log("\n--- 5. a refusal is the server's own sentence -------------------------");
  const w3 = page();
  await w3.eval("appReady");
  await w3.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  await w3.eval(`trips=[${JSON.stringify({...TRIP, start: day(-9), end: day(-1)})}]; saveTrips()`);
  w3.fetch = async () => ({ok: false, status: 422, json: async () => ({detail: "trip is over"})});
  await w3.eval(`openPacking(trips[0])`);
  await drain(); await drain();
  const err3 = w3.document.getElementById("pkErr").textContent;
  check("'trip is over' reads as a sentence, not a connection problem", /already over/.test(err3) && !/reach/.test(err3), err3);

  console.log("\n--- 6. the trip sheet accepts a trip under way, refuses one that is over");
  const w4 = page();
  await w4.eval("appReady");
  await w4.eval(`trips=[]; saveTrips()`);
  w4.eval(`tsheet={trip:{id:"x1",place:"Tokyo, Japan",lat:35.68,lon:139.77,start:"${day(-2)}",end:"${day(3)}",type:"business",styles:["casual"],packed:[],notifyDays:2}}`);
  w4.document.getElementById("tsSave").onclick();
  await drain(); await drain();
  check("a trip that started two days ago saves", w4.eval("trips.length") === 1 && !w4.document.getElementById("tsErr").textContent,
    w4.document.getElementById("tsErr").textContent);
  w4.eval(`tsheet={trip:{id:"x2",place:"Osaka, Japan",lat:34.7,lon:135.5,start:"${day(-9)}",end:"${day(-1)}",type:"vacation",styles:["casual"],packed:[],notifyDays:2}}`);
  w4.document.getElementById("tsSave").onclick();
  await drain();
  check("a trip that is over is refused", /already over/.test(w4.document.getElementById("tsErr").textContent) && w4.eval("trips.length") === 1);

  console.log("\n--- 7. the advice card says when no suitcase is declared ---------------");
  const w5 = page();
  await w5.eval("appReady");
  await w5.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  await w5.eval(`trips=[${JSON.stringify(TRIP)}]; saveTrips()`);
  w5.eval(`renderOutfit(${JSON.stringify(OUTFIT)},"words","llm",{closetUsed:true,closetSent:true,picks:{base:"t1",bottoms:"b1"}})`);
  const note = w5.document.getElementById("tripNote");
  check("the note shows, naming the trip", note.style.display !== "none" && /Tokyo/.test(note.textContent) && /nothing is marked as packed/.test(note.textContent), note.textContent);
  check("with a way to fix it", !!w5.document.getElementById("tripNoteBtn"));
  /* Declared AFTER the advice on screen was made: the card still shows the
     wardrobe's answer, so the note changes rather than disappears (the reviewer). */
  w5.eval(`lastRes={at:Date.now()-5000}`);
  await w5.eval(`trips[0].packed=[{id:"t1",qty:1}]; trips[0].packedAt=Date.now(); saveTrips()`);
  w5.eval(`renderOutfit(${JSON.stringify(OUTFIT)},"words","llm",{closetUsed:true,closetSent:true,picks:{base:"t1"}})`);
  check("advice older than the suitcase says so", note.style.display !== "none" && /before you set your suitcase/.test(note.textContent), note.textContent);
  w5.eval(`lastRes={at:Date.now()+1000}`);
  w5.eval(`renderOutfit(${JSON.stringify(OUTFIT)},"words","llm",{closetUsed:true,closetSent:true,picks:{base:"t1"}})`);
  check("and hides once fresh advice has been made from it", note.style.display === "none");
  /* Restored on launch: the record carries `at`, and it must reach lastRes, or every
     reopen after packing would ask for advice that is already from the suitcase. */
  await w5.eval(`prefSet(TODAY_KEY, JSON.stringify({day:todayISO(), at:Date.now()+2000, how:"push",
    weather:${JSON.stringify({lo:19,hi:22,desc:"Cloudy",rain:0,wind:2,code:3,emoji:"☁️",swing:3,feelsLo:18,feelsHi:23,morning:19,midday:22,evening:20,isRain:false,isSnow:false,date:day(0)})},
    outfit:${JSON.stringify(OUTFIT)}, outfit_text:"x", source:"llm", picks:{base:"t1"}, closetUsed:true, missing:[]}))`);
  await w5.eval("loadToday()");
  await drain();
  check("advice restored on launch keeps its timestamp", typeof w5.eval("lastRes.at") === "number");
  check("and is not called stale when it was made after packing", note.style.display === "none", note.textContent);
  /* Stamped at REQUEST time: a suitcase declared while the answer is in flight is
     newer than the answer, and the note must say so (the reviewer). */
  const w6 = page();
  await w6.eval("appReady");
  await w6.eval(`closet=${JSON.stringify(CLOSET)}; saveCloset()`);
  await w6.eval(`trips=[${JSON.stringify({...TRIP, packed: [{id: "t1", qty: 1}], packedAt: Date.now() - 60000})}]; saveTrips()`);
  let release; const gate = new Promise(r => { release = r; });
  w6.fetch = async (url) => { if (String(url).endsWith("/advice")) { await gate;
      return {ok: true, status: 200, json: async () => ({weather: {lo:19,hi:22,desc:"Cloudy",rain:0,wind:2,code:3,emoji:"☁️",swing:3,feelsLo:18,feelsHi:23,morning:19,midday:22,evening:20,isRain:false,isSnow:false,date:day(0)},
        outfit: OUTFIT, outfit_text: "x", source: "llm", picks: {base: "t1"}, closetUsed: true, missing: []})}; }
    return {ok: true, status: 200, json: async () => ({})}; };
  w6.eval("state.lat=35.68; state.lon=139.77; state.city=''");
  const pending = w6.eval("run()");
  await drain();
  await w6.eval(`trips[0].packed=[{id:"t2",qty:1}]; trips[0].packedAt=Date.now()+1; saveTrips()`);   // repacked mid-flight
  release(); await pending; await drain();
  const n6 = w6.document.getElementById("tripNote");
  check("advice requested before a repack is called stale even though it arrived after",
    n6.style.display !== "none" && /before you set your suitcase/.test(n6.textContent), n6.textContent);
  await w5.eval(`trips[0].start="${day(-7)}"; wearLog=[{itemId:"t1",wornAt:Date.now()-4*86400000}]; saveTrips()`);
  const avail = JSON.parse(w5.eval("JSON.stringify(packPayload(trips[0]))")).find(i => i.id === "t1");
  check("on a trip under way, availability is judged from today, not departure", !!avail && avail.availableCount === 2, avail);

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
