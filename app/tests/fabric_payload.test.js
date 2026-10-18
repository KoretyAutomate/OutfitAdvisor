/**
 * fabric_payload.test.js — the garment's fabric reaches the advisor (user, 2026-10-18:
 * "Fabric of polo and sweater doesn't go well"). The photo scan reads it from a care
 * label; the request never carried it, so the advisor and its stylist could not see it.
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

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true}).window;
  await w.eval("appReady");
  const it = (id, extra) => ({id, label: id, category: "base", group: "tops", type: "polo", roles: ["base"],
    colors: ["navy"], warmth: 2, formality: ["casual"], waterproof: false, count: 1, ...extra});
  await w.eval(`closet=${JSON.stringify([it("knitpolo", {fabric: "knit"}), it("plain", {})])}; wearLog=[]`);
  const sent = JSON.parse(w.eval("JSON.stringify(closetPayload())"));
  const by = Object.fromEntries(sent.map(i => [i.id, i]));
  check("a known fabric is sent", by.knitpolo && by.knitpolo.fabric === "knit", by.knitpolo);
  check("an unknown one is left out, not sent empty", by.plain && !("fabric" in by.plain), by.plain);
  console.log(`\nfabric_payload: ${passed} passed, ${failed} failed`);
  if (failed) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
