/**
 * feels_like.test.js — dress for how the day FEELS (user, 2026-10-10): "feels like
 * temperature between 8am and 7pm unless there is an event in our calendar".
 *
 * Pinned (twin of server/tests/test_feels_like.py, same hours, same answers):
 *   - an hour counts as it feels, at most 4° colder / 3° warmer than the air;
 *   - the day is 08:00-19:00; an evening event the phone reads stretches it;
 *   - the offline recommender dresses for the coldest felt hour;
 *   - /advice is told the evening hour (and nothing else), only when there is one;
 *   - the weather card says what the outfit was dressed for.
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
const HOURS = [[8, 14.0, 8.0], [10, 16.0, 13.0], [13, 20.0, 24.5], [16, 18.0, 17.0],
  [19, 15.0, 13.0], [20, 13.0, 11.0], [22, 11.0, 9.0], [23, 10.0, 8.0]];
const day = (extra = {}) => ({date: "2026-10-10", code: 3, emoji: "☁", desc: "Overcast", lo: 10, hi: 20,
  swing: 10, feelsLo: 8, feelsHi: 25, rain: 0, wind: 9, morning: 14, midday: 20, evening: 15,
  isSnow: false, isRain: false, hours: HOURS, ...extra});

(async () => {
  const w = new JSDOM(fs.readFileSync(HTML, "utf8"), {
    runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
  }).window;
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const J = JSON.stringify;

  console.log("\n--- 1. the window, as the server computes it --------------------------");
  check("felt hours are bounded", ev("felt(14,8)") === 10 && ev("felt(20,24.5)") === 23
    && ev("felt(16,13)") === 13 && ev("felt(16,null)") === 16);
  const d = ev(`planWindow(${J(day())})`);
  check("8-19 by default: coldest 10, warmest 23", d.planLo === 10 && d.planHi === 23 && d.planUntil === 19, d);
  check("an event to 22:00 reaches the 9° evening", ev(`planWindow(${J(day())},22).planLo`) === 9);
  check("to midnight reaches 23:00", ev(`planWindow(${J(day())},24).planLo`) === 8);
  check("no hourly data: the morning still decides",
    ev(`planTemp(planWindow(${J(day({hours: []}))}))`) === 14);
  check("the thermal offset moves the window too",
    ev(`applyTempOffset(planWindow(${J(day())}),2).planLo`) === 12);

  console.log("\n--- 2. the offline recommender ---------------------------------------");
  const mild = day({morning: 16, hours: [[8, 16, 16], [19, 16, 16]]});
  const raw = day({morning: 16, hours: [[8, 16, 10], [19, 8, 4]]});
  check("a mild felt day gets a light inner",
    /Light/.test(ev(`recommend(planWindow(${J(mild)}),"man","casual").inner`)));
  check("the same 16° morning that feels raw, cooling to 4°, gets a thermal",
    /thermal/i.test(ev(`recommend(planWindow(${J(raw)}),"man","casual").inner`)));

  console.log("\n--- 3. the calendar hour reaches /advice ------------------------------");
  const bodies = [];
  w.fetch = async (url, opts) => {
    if (String(url).includes("/advice")) {
      bodies.push(JSON.parse(opts.body));
      return {ok: true, status: 200, json: async () => ({weather: day(), outfit: {}, outfit_text: "", source: "llm",
        missing: [], planTemp: 9, peakTemp: 23})};
    }
    throw new Error("unexpected " + url);
  };
  ev("Plugins.OutfitAlarm=Plugins.OutfitAlarm||{}");
  ev("Plugins.OutfitAlarm.eveningOut=async()=>({until:22})");
  await ev("getAdvice(40.3,-74.6)");
  check("an evening event sends its end hour", bodies[0].outUntil === 22, bodies[0]);
  check("…and nothing about the event itself",
    !Object.keys(bodies[0]).some(k => /title|location|event/i.test(k)), Object.keys(bodies[0]));
  ev("Plugins.OutfitAlarm.eveningOut=async()=>({})");
  await ev("getAdvice(40.3,-74.6)");
  check("no evening event: no field", !("outUntil" in bodies[1]), bodies[1]);
  ev("Plugins.OutfitAlarm.eveningOut=async()=>{throw new Error('denied')}");
  await ev("getAdvice(40.3,-74.6)");
  check("a calendar that cannot be read costs nothing", bodies.length === 3 && !("outUntil" in bodies[2]));
  ev("delete Plugins.OutfitAlarm.eveningOut");
  check("an older build without the method: null", (await ev("eveningOut()")) === null);

  console.log("\n--- 4. offline, the phone plans the same window ----------------------");
  ev("Plugins.OutfitAlarm.eveningOut=async()=>({until:22})");
  const om = {daily: {time: ["2026-10-10"], weather_code: [3], temperature_2m_max: [20], temperature_2m_min: [10],
    apparent_temperature_max: [25], apparent_temperature_min: [8], precipitation_probability_max: [0],
    wind_speed_10m_max: [9]}, hourly: {time: [], temperature_2m: [], apparent_temperature: []}, timezone: "UTC"};
  for (let h = 0; h < 24; h++) {
    const hit = HOURS.find(x => x[0] === h);
    om.hourly.time.push(`2026-10-10T${String(h).padStart(2, "0")}:00`);
    om.hourly.temperature_2m.push(hit ? hit[1] : 15);
    om.hourly.apparent_temperature.push(hit ? hit[2] : 15);
  }
  w.fetch = async url => {
    if (String(url).includes("open-meteo")) return {ok: true, status: 200, json: async () => om};
    throw new Error("server down");
  };
  const off = await ev("getAdvice(40.3,-74.6)");
  check("the offline answer is planned to 22:00 from the live hourly feels-like",
    off.source === "offline" && off.weather.planUntil === 22 && off.weather.planLo === 9, off.weather);

  console.log("\n--- 5. the weather card says what it dressed for ----------------------");
  ev(`renderWeather(${J(ev(`planWindow(${J(day())},22)`))})`);
  const line = w.document.getElementById("wxPlan").textContent;
  check("the card names the felt range and the evening", /9°–23°/.test(line) && /22:00/.test(line)
    && /calendar/.test(line), line);
  ev(`renderWeather(${J(ev(`planWindow(${J(day())})`))})`);
  check("an ordinary day does not mention the calendar",
    !/calendar/.test(w.document.getElementById("wxPlan").textContent));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
