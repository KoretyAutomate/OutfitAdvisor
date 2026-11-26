/**
 * calendar_day_off.test.js — a day off by the calendar (user, 2026-11-26: "I have a
 * day off today and it's Thanksgiving" — the office days said Office; "Both public
 * holidays and my entry for the calendar").
 *
 * Pinned:
 *   - a day off from DayOff.kt (holiday or their own entry) beats the office days,
 *     for today only, and the request asks for "off" with the home style;
 *   - the Today screen's one-day override still beats the calendar;
 *   - the note names the reason; nothing but the kind leaves the phone;
 *   - no plugin, a failing plugin, or {off:false} changes nothing;
 *   - the morning push (Kotlin) checks the calendar after the override and before
 *     the office days;
 *   - DayOff.kt's title and observance patterns (lifted from the source, run here).
 *
 * Loads the REAL app/www/index.html in jsdom. Run: npm test
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "www", "index.html");
const SRC = path.join(__dirname, "..", "android", "app", "src", "main", "java", "com", "korety", "outfitadvisor");
let passed = 0, failed = 0;
const check = (name, cond, detail = "") => {
  if (cond) { passed++; console.log(`[PASS] ${name}`); }
  else { failed++; console.log(`[FAIL] ${name}  ${JSON.stringify(detail)}`); }
};
const WX = {lo: 2, hi: 8, desc: "Rain", rain: 90, wind: 5, code: 63, emoji: "🌧️", swing: 6, feelsLo: 0,
  feelsHi: 6, morning: 3, midday: 6, evening: 5, isRain: true, isSnow: false, date: "2026-11-26"};

/** A Kotlin Regex("…" + "…", IGNORE_CASE) declared as `private val NAME`, as a JS RegExp. */
function kotlinRegex(src, name) {
  let body = src.slice(src.indexOf(`private val ${name} = Regex(`));
  body = body.slice(0, body.indexOf("RegexOption"));
  const parts = [...body.matchAll(/"((?:[^"\\]|\\.)*)"/g)].map(m => JSON.parse(`"${m[1]}"`));
  return new RegExp(parts.join(""), "iu");
}

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const dow = new Date().getDay();

  ev(`state.style="casual"; state.styleOffice="smart"; state.lat=40.3; state.lon=-74.6;
      state.officeDays=[${dow}]; dayKindOverride=null;
      fetchWeatherLocal = async () => (${JSON.stringify(WX)});
      fetch = async (u, o) => { if (o && o.body) window.__b = JSON.parse(o.body); throw new Error("stop"); };`);
  // As run() does: the calendar first, then the request.
  const ask = async () => { ev("window.__b=null"); try { await ev("refreshDayOff().then(()=>{paintDay(); return getAdvice(40.3,-74.6);})"); } catch (e) {} return ev("window.__b"); };
  const plugin = js => ev(`Plugins.OutfitAlarm = Object.assign(Plugins.OutfitAlarm||{}, {dayOff: ${js}})`);

  console.log("\n--- 1. no calendar signal ------------------------------------------");
  let b = await ask();
  check("no dayOff plugin: today's office day stands", b.occasion === "office" && b.style === "smart", b);
  plugin(`async () => ({off: false})`);
  b = await ask();
  check("{off:false}: the office day stands", b.occasion === "office", b);
  plugin(`async () => { throw new Error("no permission"); }`);
  b = await ask();
  check("a failing plugin: the office day stands", b.occasion === "office", b);

  console.log("\n--- 2. a public holiday ---------------------------------------------");
  plugin(`async () => ({off: true, source: "holiday", label: "Thanksgiving Day"})`);
  b = await ask();
  check("Thanksgiving on an office day asks for a day off, home style", b.occasion === "off" && b.style === "casual", b);
  check("only the kind leaves the phone, never the title", !JSON.stringify(b).includes("Thanksgiving"), b);
  check("the note names the holiday", ev(`$("kindNote").textContent`).includes("Thanksgiving Day, from your calendar"),
    ev(`$("kindNote").textContent`));
  check("the Off button is lit", ev(`[...$("kindSeg").children].find(b=>b.classList.contains("on"))?.dataset.k`) === "off");
  const other = new Date(); other.setDate(other.getDate() + 7);
  check("another date is not today's holiday", ev(`scheduledKind(new Date(${other.getTime()}))`) === "office");
  ev(`calendarOff={...calendarOff, day:"2000-01-01"}`);
  check("yesterday's reading is not today's", ev("dayKind()") === "office");

  console.log("\n--- 3. their own entry, and the override -----------------------------");
  plugin(`async () => ({off: true, source: "entry", label: ""})`);
  b = await ask();
  check("their time-off entry makes it a day off", b.occasion === "off", b);
  check("an entry without a title still says why", ev(`$("kindNote").textContent`).includes("your time off, from your calendar"));
  ev(`dayKindOverride={day:todayISO(), kind:"office"}`);
  b = await ask();
  check("the Today screen's tap still wins over the calendar", b.occasion === "office" && b.style === "smart", b);
  ev(`dayKindOverride=null`);

  console.log("\n--- 3b. the calendar is read before anything is judged by it ---------");
  const html = fs.readFileSync(HTML, "utf8");
  const runFn = html.slice(html.indexOf("async function run(){"));
  check("run() reads the calendar before it records what the request is for",
    runFn.indexOf("await refreshDayOff()") > 0 && runFn.indexOf("await refreshDayOff()") < runFn.indexOf("runPendingFor=dayPair()"));
  const vis = html.slice(html.indexOf('document.addEventListener("visibilitychange"'));
  check("on resume, before the advice is re-checked",
    vis.indexOf("await refreshDayOff()") > 0 && vis.indexOf("await refreshDayOff()") < vis.indexOf("refreshForDay(false)"));
  const boot = html.slice(html.indexOf("const appReady=(async()=>{"));
  check("at start-up, before today's saved advice is restored",
    boot.indexOf("await refreshDayOff()") > 0 && boot.indexOf("await refreshDayOff()") < boot.indexOf("await loadToday()"));
  // Behaviour: a morning-push record saved as a day off is restored on a holiday.
  ev(`dayKindOverride=null; calendarOff=null;`);
  plugin(`async () => ({off: true, source: "holiday", label: "Thanksgiving Day"})`);
  w.localStorage.setItem("oa.today", JSON.stringify({day: ev("todayISO()"), outfit: {base: "grey tee"}, outfit_text: "• Grey tee",
    picks: {base: "i1"}, closetUsed: true, weather: WX, occasion: "off", style: "casual"}));
  check("holiday advice from the morning push is restored once the calendar is read",
    await ev("refreshDayOff().then(()=>loadToday())") === true);

  // Ticking or unticking calendars re-reads today and re-judges the advice.
  ev(`window.__dayOffCalls=0; Plugins.OutfitAlarm.dayOff=async()=>{ window.__dayOffCalls++; return {off:false}; };
      calendarOff={day:todayISO(),source:"entry",label:"PTO"}; window.__rfd=0;
      { const real=refreshForDay; refreshForDay=(c)=>{ window.__rfd++; return real(c); }; }`);
  ev(`document.getElementById("calList").innerHTML='<input type="checkbox" data-cal="1">'`);
  await ev("saveCalSel()");
  check("saving the calendar ticks re-reads today's day off", ev("window.__dayOffCalls") >= 1 && ev("dayKind()") === "office",
    {calls: ev("window.__dayOffCalls"), kind: ev("dayKind()")});
  check("…and re-judges the advice on screen", ev("window.__rfd") >= 1);

  console.log("\n--- 4. the morning push (Kotlin twin) --------------------------------");
  const worker = fs.readFileSync(path.join(SRC, "AdviceWorker.kt"), "utf8");
  const fn = worker.slice(worker.indexOf("private fun dayKind("));
  const iOverride = fn.indexOf('o.optString("day") == today()'), iCal = fn.indexOf("if (calendarOff) return \"off\"");
  const iDays = fn.indexOf('"oa.officeDays"');
  check("the worker checks the calendar after the override, before the office days",
    iOverride > 0 && iCal > iOverride && iDays > iCal, {iOverride, iCal, iDays});
  check("the worker asks DayOff", worker.includes("dayKind(prefs, DayOff.today(applicationContext) != null)"));
  const plug = fs.readFileSync(path.join(SRC, "OutfitAlarmPlugin.kt"), "utf8");
  check("the plugin exposes dayOff", /fun dayOff\(call: PluginCall\)[\s\S]{0,300}DayOff\.today\(context\)/.test(plug));

  console.log("\n--- 5. DayOff.kt's patterns ------------------------------------------");
  const day = fs.readFileSync(path.join(SRC, "DayOff.kt"), "utf8");
  const off = kotlinRegex(day, "TIME_OFF"), not = kotlinRegex(day, "NOT_OFF"), obs = kotlinRegex(day, "OBSERVANCE");
  const says = t => off.test(t.normalize("NFKC")) && !not.test(t.normalize("NFKC"));
  for (const t of ["Day off", "day-off", "Off", "PTO", "Vacation in Hawaii", "Out of office", "OOO", "Sick day",
                   "Annual leave", "有給", "お休み", "夏休み", "代休", "オフ", "ＰＴＯ"])
    check(`time off: ${t}`, says(t), t);
  for (const t of ["Office", "Office day", "Kick-off", "PTO planning", "Holiday party", "Team lunch", "Coffee",
                   "オフィス出社", "オフ会", "有給申請", "Offsite", "Trade-off review", "Dentist"])
    check(`not time off: ${t}`, !says(t), t);
  check("Google's observance description is skipped",
    obs.test("Observance\nTo hide observances, go to Google Calendar Settings > Holidays in United States"));
  check("a public holiday's description is not", !obs.test("Public holiday"));
  check("holiday calendars by owner, case-insensitive",
    /endsWith\(HOLIDAY_OWNER\)/.test(day) && day.includes('"#holiday@group.v.calendar.google.com"') && day.includes("lowercase("));
  check("own entries never from a shared calendar", day.includes("EveningOut.allowedCalendars(ctx, shared = false)"));
  check("all-day dates are read in UTC", /if \(allDay\) \{\s*val utc = TimeZone\.getTimeZone\("UTC"\)/.test(day));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
