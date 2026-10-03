/**
 * laundry_loads.test.js — washing by LOAD, and drying (user, 2026-10-03): "My
 * household has split rules into 1) white 2) light color 3) colorful colors 4) dark
 * color. When I click on laundry done, I want to pick which split of laundry is
 * done ... it's more realistic to assume laundry done as finished washing but not
 * yet dry."
 *
 * Pinned:
 *   - each garment's load, read off its main colour unless chosen by hand;
 *   - "Laundry done" washes only the ticked loads, never today's clothes;
 *   - washed is not wearable until dry — the tile says "drying" — and is after;
 *   - the drying time is a setting, and 0 means straight back;
 *   - the push payload says WHEN each held unit comes free, so the worker can count
 *     what dried overnight;
 *   - a wear that is still drying survives the wear-log prune.
 *
 * Loads the REAL app/www/index.html in jsdom. Run: npm test
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
const H = 3600000, D = 24 * H;

const item = (id, label, colors, extra = {}) => ({id, label, category: "base", group: "tops",
  type: "t_shirt", roles: ["base"], colors, warmth: 1, formality: ["casual"], waterproof: false,
  count: 1, ...extra});

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const realNow = w.Date.now.bind(w.Date);
  let T = realNow();
  w.Date.now = () => T;

  console.log("\n--- 1. which load a garment goes in --------------------------------");
  const L = (colors, extra = {}) => ev(`loadOf(${JSON.stringify(item("x", "x", colors, extra))})`);
  check("white → Whites", L(["white"]) === "white");
  check("off-white → Whites", L(["off-white"]) === "white");
  check("beige → Light colours", L(["beige"]) === "light");
  check("light grey → Light colours", L(["light grey"]) === "light");
  check("navy → Darks", L(["navy"]) === "dark");
  check("grey → Darks", L(["grey"]) === "dark");
  check("black → Darks", L(["black", "white"]) === "dark");
  check("red → Colourful", L(["red"]) === "colorful");
  check("the MAIN colour decides: white with navy stripes is a white",
    L(["white", "navy"]) === "white");
  check("a chosen load beats the colour", L(["white"], {load: "dark"}) === "dark");
  check("no colour at all → Colourful", L([]) === "colorful");

  console.log("\n--- 2. Laundry done asks which loads -------------------------------");
  const yesterday = T - D;
  await ev(`closet=[${JSON.stringify(item("w1", "white tee", ["white"]))},
    ${JSON.stringify(item("d1", "navy tee", ["navy"]))},
    ${JSON.stringify(item("c1", "red tee", ["red"]))}];
    wearLog=[{itemId:"w1",wornAt:${yesterday}},{itemId:"d1",wornAt:${yesterday}},
             {itemId:"c1",wornAt:${T}}]; saveCloset()`);
  w.document.getElementById("laundryBtn").onclick(); await drain();
  const box = l => w.document.querySelector(`#washLoads input[data-load="${l}"]`);
  check("the picker opens", w.document.getElementById("washWrap").classList.contains("show"));
  check("loads with something waiting start ticked", box("white").checked && box("dark").checked);
  check("today's clothes are not waiting — that shirt is still on you",
    box("colorful").disabled && !box("colorful").checked);
  check("an empty load cannot be picked", box("light").disabled);
  box("dark").checked = false; box("dark").onchange();
  await w.document.getElementById("washGo").onclick(); await drain();
  const log = JSON.parse(ev("JSON.stringify(wearLog)"));
  const of = id => log.find(x => x.itemId === id);
  check("only the ticked load is washed", of("w1").washedAt === T && of("d1").washedAt == null, log);
  check("today's wear is untouched", of("c1") && of("c1").washedAt == null);

  console.log("\n--- 3. washed is not dry ------------------------------------------");
  check("a washed white tee is still out while it dries", ev(`avail(closet[0])`) === 0);
  await ev("renderCloset()"); await drain();
  const tile = id => w.document.querySelector(`.item[data-id="${id}"]`);
  check("its tile says drying", /drying/.test(tile("w1")?.textContent || ""), tile("w1")?.textContent);
  check("the unwashed navy tee says wash", /wash/.test(tile("d1")?.textContent || "")
    && !/drying/.test(tile("d1")?.textContent || ""));
  T += 23 * H;
  check("still wet at 23 hours", ev(`avail(closet[0])`) === 0);
  T += 2 * H;
  check("dry and back after the default day", ev(`avail(closet[0])`) === 1);

  console.log("\n--- 4. the drying time is a setting --------------------------------");
  T = realNow();
  await ev(`closet=[${JSON.stringify(item("w2", "white tee", ["white"]))}];
    wearLog=[{itemId:"w2",wornAt:${T - D}}]; saveCloset()`);
  w.document.getElementById("dryHours").value = "0";
  await w.document.getElementById("dryHours").onchange(); await drain();
  w.document.getElementById("laundryBtn").onclick(); await drain();
  await w.document.getElementById("washGo").onclick(); await drain();
  check("a tumble dryer puts it straight back", ev(`avail(closet[0])`) === 1);
  const stored = JSON.parse(await ev(`prefGet("oa.laundry","{}")`));
  check("the setting is stored", stored.dryHours === 0, stored);
  w.document.getElementById("dryHours").value = "24";
  await w.document.getElementById("dryHours").onchange(); await drain();

  console.log("\n--- 5. the wear log keeps what is still drying ---------------------");
  T = realNow();
  await ev(`closet=[${JSON.stringify(item("p1", "white tee", ["white"]))}];
    wearLog=[{itemId:"p1",wornAt:${T - 6 * D},washedAt:${T - H}}]; saveCloset()`);
  check("worn six days ago, washed an hour ago: kept, and still out",
    ev("wearLog.length") === 1 && ev(`avail(closet[0])`) === 0);
  await ev(`wearLog=[{itemId:"p1",wornAt:${T - 6 * D}}]; saveCloset()`);
  check("worn six days ago, never washed: back on the passive timer, and pruned",
    ev("wearLog.length") === 0 && ev(`avail(closet[0])`) === 1);

  // An expired wear still in the log (pruned only on a write) is clean already.
  T = realNow();
  await ev(`closet=[${JSON.stringify(item("e1", "white tee", ["white"]))},
    ${JSON.stringify(item("e2", "white shirt", ["white"]))}]; saveCloset();
    wearLog=[{itemId:"e1",wornAt:${T - 6 * D}},{itemId:"e2",wornAt:${T - D}}]`);
  w.document.getElementById("laundryBtn").onclick(); await drain();
  await w.document.getElementById("washGo").onclick(); await drain();
  check("washing never sends a garment that was already clean back to drying",
    ev(`avail(closet.find(i=>i.id==="e1"))`) === 1 && ev(`avail(closet.find(i=>i.id==="e2"))`) === 0);

  console.log("\n--- 6. the push payload says when things come free ------------------");
  T = realNow();
  await ev(`closet=[${JSON.stringify(item("q1", "white tee", ["white"]))},
    ${JSON.stringify(item("q2", "navy tee", ["navy"], {count: 2}))},
    ${JSON.stringify(item("q3", "red tee", ["red"]))}];
    wearLog=[{itemId:"q1",wornAt:${T - D},washedAt:${T - H}},
             {itemId:"q2",wornAt:${T - D}}]; saveCloset()`);
  const pay = JSON.parse(await ev(`prefGet("oa.pushPayload","{}")`));
  const pend = pay.pending || [], cl = pay.closet || [];
  const q1 = pend.find(i => i.id === "q1"), q2 = cl.find(i => i.id === "q2");
  check("a garment with nothing free yet travels in pending, at 0",
    q1 && q1.availableCount === 0 && !cl.some(i => i.id === "q1"), pay);
  check("…with the moment it is dry", q1 && q1.freeAt.length === 1 && q1.freeAt[0] === T - H + 24 * H, q1);
  check("a garment partly out says when its other unit comes back",
    q2 && q2.availableCount === 1 && q2.freeAt[0] === T - D + 4 * D, q2);
  check("a garment with nothing held carries no times",
    cl.find(i => i.id === "q3") && !("freeAt" in cl.find(i => i.id === "q3")));
  check("pending is built from the same shape the server takes",
    q1 && q1.label === "white tee" && q1.category === "base" && Array.isArray(q1.roles));

  await ev(`userRules=[{id:"r1",kind:"never",a:"q1",text:"never the white tee"}];
    closet=[${JSON.stringify(item("q1", "white tee", ["white"]))}];
    wearLog=[{itemId:"q1",wornAt:${T - D},washedAt:${T - H}}]; saveCloset()`);
  const allWet = JSON.parse(await ev(`prefGet("oa.pushPayload","{}")`));
  check("everything drying still carries the rules, for when it is dry",
    allWet.closet.length === 0 && allWet.pending.length === 1 && allWet.rules.length === 1, allWet);
  await ev(`userRules=[]`);
  // A favourite drying tonight: its preference must travel with it.
  await ev(`swaps=[{slot:"base",wore:"q1",day:todayISO()},{slot:"base",wore:"q1",day:todayISO()}];
    savePushPayload()`); await drain();
  const prefIds = JSON.parse(await ev(`prefGet("oa.pushPayload","{}")`)).prefers.map(p => p.id);
  await ev("swaps=[]");
  check("a drying favourite keeps its preference for the worker to filter", prefIds.includes("q1"), prefIds);

  console.log("\n--- 7. the load in the edit sheet ----------------------------------");
  await ev(`closet=[${JSON.stringify(item("s1", "white tee", ["white"]))}]; saveCloset()`);
  await ev(`openSheet(closet[0],{isNew:false})`); await drain();
  const sel = w.document.getElementById("shLoad");
  check("automatic is the default, and says what it means", sel.value === ""
    && /Automatic — Whites/.test(sel.options[0].textContent), sel.options[0].textContent);
  sel.value = "light";
  await w.document.getElementById("shSave").onclick(); await drain();
  check("a chosen load is saved", ev("closet[0].load") === "light");
  await ev(`openSheet(closet[0],{isNew:false})`); await drain();
  w.document.getElementById("shLoad").value = "";
  await w.document.getElementById("shSave").onclick(); await drain();
  check("back to automatic stores nothing", ev("closet[0].load") === undefined);

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
