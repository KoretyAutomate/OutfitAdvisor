/**
 * self_update.test.js — updates that install themselves (user, 2026-11-21: "avoid
 * requiring me to hit install and still update"). The install is native
 * (SelfUpdate.kt); what the web layer owns is pinned here:
 *   - the Install tap passes versionName, which the native side stamps for the
 *     "Updated to vX" notice;
 *   - a started install says the app will close, never "the installer is asking";
 *   - needs-permission still routes to the one-time grant;
 *   - a failed automatic attempt (lastError) stays visible in Settings;
 *   - an up-to-date build says updates install by themselves.
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
const drain = () => new Promise(r => setTimeout(r, 0));

/* A page whose native AppUpdate plugin is a fake. `cur` is what current() returns,
   `published` what GET /version returns, `result` what install() resolves with. */
function page({ cur, published, result = { status: "installing" } }) {
  const calls = [];
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
    beforeParse(win) {
      win.Capacitor = { isNativePlatform: () => false, Plugins: { AppUpdate: {
        current: async () => cur,
        install: async (o) => { calls.push(o); return result; },
      } } };
      win.fetch = async (url) => {
        if (String(url).endsWith("/version"))
          return { ok: !!published, json: async () => published };
        return { ok: false, json: async () => ({}) };
      };
    },
  }).window;
  return { w, calls };
}

const CUR = { versionCode: 60, versionName: "1.60", canInstall: true, lastError: "" };
const NEXT = { versionCode: 61, versionName: "1.61", sha256: "ab".repeat(32), size: 15_000_000 };

(async () => {
  // Up to date: says updates install by themselves, offers no button.
  {
    const { w } = page({ cur: CUR, published: { ...NEXT, versionCode: 60, versionName: "1.60" } });
    await drain(); await w.renderVersion(); await drain();
    const line = w.document.getElementById("verLine").textContent;
    check("up to date says updates install by themselves", /install by themselves/.test(line), line);
    check("up to date shows no Install button",
      w.document.getElementById("verInstall").style.display === "none");
  }

  // Newer build, tap Install: versionName and checksum reach the native side; the
  // card says the app will close.
  {
    const { w, calls } = page({ cur: CUR, published: NEXT });
    await drain(); await w.renderVersion(); await w.doUpdate(); await drain();
    const c = calls[0] || {};
    check("install receives versionName", c.versionName === "1.61", c);
    check("install still receives sha256 and size", c.sha256 === NEXT.sha256 && c.size === NEXT.size, c);
    check("install targets /apk", /\/apk$/.test(c.url || ""), c.url);
    const msg = w.document.getElementById("verMsg").textContent;
    check("started install says the app will close", /app will close/.test(msg), msg);
    check("started install no longer claims the installer is asking", !/installer should be asking/.test(msg), msg);
  }

  // No grant yet: still routes to the one-time toggle.
  {
    const { w } = page({ cur: { ...CUR, canInstall: false }, published: NEXT,
                         result: { status: "needs-permission" } });
    await drain(); await w.renderVersion(); await w.doUpdate(); await drain();
    const msg = w.document.getElementById("verMsg").textContent;
    check("needs-permission asks for the grant", /Allow from this source/.test(msg), msg);
  }

  // An automatic attempt failed: the reason stays on screen.
  {
    const { w } = page({ cur: { ...CUR, lastError: "install failed (3): blocked" }, published: NEXT });
    await drain(); await w.renderVersion(); await drain();
    const msg = w.document.getElementById("verMsg");
    check("last error is shown", msg.style.display === "block" && /install failed \(3\): blocked/.test(msg.textContent),
      msg.textContent);
  }

  // A failed tap is written into the card.
  {
    const { w } = page({ cur: CUR, published: NEXT });
    w.Capacitor.Plugins.AppUpdate.install = async () => { throw new Error("checksum mismatch"); };
    await drain(); await w.renderVersion(); await w.doUpdate(); await drain();
    const msg = w.document.getElementById("verMsg").textContent;
    check("failed install is written into the card", /Update failed: checksum mismatch/.test(msg), msg);
  }

  // Android rejects the install after "installing" was reported: the open card
  // finds out and says so (the receiver records lastError; current() carries it).
  {
    let calls = 0;
    const { w } = page({ cur: CUR, published: NEXT });
    w.Capacitor.Plugins.AppUpdate.current = async () =>
      (++calls > 3 ? { ...CUR, lastError: "install failed (4): signatures do not match" } : CUR);
    w.eval("UPD_WATCH_MS=1; UPD_WATCH_TRIES=10;");
    await drain(); await w.renderVersion(); await w.doUpdate(); await drain();
    const msg = w.document.getElementById("verMsg").textContent;
    check("a later install rejection replaces 'will close'",
      /Update failed: install failed \(4\): signatures do not match/.test(msg), msg);
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
