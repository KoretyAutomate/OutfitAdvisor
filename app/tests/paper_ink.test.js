/**
 * paper_ink.test.js — the redesign's tokens, pinned (2026-09-07).
 *
 * The old stylesheet matched seven published "AI design slop" tells: dark slate,
 * grey body text, uppercase letter-spaced labels, a cyan→indigo gradient button,
 * lavender as the second accent, a glowing toggle, pill chips, emoji tab icons.
 * These checks read the REAL index.html so none of them can return quietly.
 *
 * Run: npm test   (or: node tests/paper_ink.test.js)
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
const html = fs.readFileSync(HTML, "utf8");
let passed = 0, failed = 0;
const check = (name, cond, detail = "") => {
  if (cond) { passed++; console.log(`[PASS] ${name}`); }
  else { failed++; console.log(`[FAIL] ${name}  ${JSON.stringify(detail)}`); }
};

(async () => {
  console.log("\n--- 1. the stylesheet has none of the old habits ---------------");
  const css = html.match(/<style>([\s\S]*?)<\/style>/)[1];
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, "");
  check("no gradients", !/gradient\(/.test(bare));
  check("no box-shadow", !/box-shadow/.test(bare));
  check("no pill radius", !/border-radius:\s*999px/.test(bare));
  check("no uppercase labels", !/text-transform:\s*uppercase/.test(bare));
  check("no letter-spacing tricks", !/letter-spacing:\s*\.0[3-9]em/.test(bare));
  check("paper ground and ink text", /--bg:#FCFBF9/.test(bare) && /--txt:#1F1D1B/.test(bare));
  check("the font is bundled, not fetched", /@font-face/.test(bare) && /url\(fonts\/figtree-latin\.woff2\)/.test(bare)
    && !/fonts\.googleapis|fonts\.gstatic/.test(html));
  check("and the font file ships with the page",
    fs.existsSync(path.join(__dirname, "..", "www", "fonts", "figtree-latin.woff2")));
  check("theme colour matches the ground", /<meta name="theme-color" content="#FCFBF9">/.test(html));

  console.log("\n--- 2. icons are drawn, not typed ---------------------------------");
  const dom = new JSDOM(html, { runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  await w.eval("appReady");
  const emoji = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
  const tabs = [...doc.querySelectorAll("#tabBar button")];
  check("three tabs, each with an inline SVG", tabs.length === 3 && tabs.every(b => b.querySelector("svg")));
  check("and no emoji in a tab label", tabs.every(b => !emoji.test(b.textContent)), tabs.map(b => b.textContent));
  check("the gear is an SVG button", !!doc.querySelector("#gearBtn svg") && !emoji.test(doc.getElementById("gearBtn").textContent));
  const statics = ["addCamBtn", "addGalBtn", "laundryBtn", "calBtn", "dShare", "dNotify", "shopBtn", "rescanBtn", "shCam", "shGal", "shWear"];
  const withEmoji = statics.filter(id => emoji.test(doc.getElementById(id).textContent));
  check("static action buttons carry words only", withEmoji.length === 0, withEmoji);
  const segs = [...doc.querySelectorAll('.seg button[data-g]')];
  check("gender segments are words only", segs.every(b => !emoji.test(b.textContent)), segs.map(b => b.textContent));

  console.log("\n--- 3. the day's accent follows the forecast ---------------------");
  const WX = {lo:14, hi:25, desc:"Clear", rain:0, wind:2, code:0, emoji:"☀️", swing:11, feelsLo:13, feelsHi:26,
    morning:16, midday:24, evening:21, isRain:false, isSnow:false, date:"2026-09-08"};
  w.eval(`renderWeather(${JSON.stringify(WX)})`);
  check("a warm afternoon is terracotta", doc.documentElement.style.getPropertyValue("--accent") === "#B4531B");
  w.eval(`renderWeather(${JSON.stringify({...WX, lo:-2, hi:5})})`);
  check("a cold day is slate", doc.documentElement.style.getPropertyValue("--accent") === "#4A6FA5");
  w.eval(`renderWeather(${JSON.stringify({...WX, lo:8, hi:17})})`);
  check("and a mild one is sage", doc.documentElement.style.getPropertyValue("--accent") === "#6E7F5A");
  check("the accent has somewhere to go", /\.wx \.big::after[^}]*var\(--accent\)/.test(bare));

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
