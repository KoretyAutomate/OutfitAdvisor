/**
 * laundry_rules.test.js — the household picks its own laundry split logic (user,
 * 2026-10-09): "first let the user pick their laundry split logic, and the field
 * should only appear if they selected ... I don't need a field for dirtiness and
 * item kind which we should still build the functionality though."
 *
 * Pinned:
 *   - splits are ticked in Settings; loads show conditions for ticked splits only;
 *   - the garment sheet shows Fabric / Weight / Dirt fields only when ticked;
 *   - matching: first load in order whose every condition holds, else catch-all;
 *     a condition on an unticked split is ignored; unknown fabric is never delicate;
 *   - weight, dirt and kind work with no field at all;
 *   - old saved loads (colours at top level) migrate; hand-picked loads still win;
 *   - "Laundry done" opens even with nothing waiting, and says how clothes get in.
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
const page = () => new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
}).window;
const item = (id, colors, extra = {}) => ({id, label: id, category: "base", group: "tops",
  type: "t_shirt", roles: ["base"], colors, warmth: 1, formality: ["casual"], waterproof: false,
  count: 1, ...extra});

(async () => {
  const w = page();
  await w.eval("appReady");
  const ev = s => w.eval(s);
  const $ = id => w.document.getElementById(id);
  const loadOf = it => ev(`loadOf(${JSON.stringify(it)})`);

  console.log("\n--- 1. the default is the four colour loads --------------------------");
  check("only Colour is ticked", ev("laundry.splits.join()") === "colour");
  check("navy → Darks, white → Whites, red → Colourful",
    loadOf(item("a", ["navy"])) === "dark" && loadOf(item("b", ["white"])) === "white"
    && loadOf(item("c", ["red"])) === "colorful");
  check("dark pink is dark, light grey is light",
    loadOf(item("d", ["dark pink"])) === "dark" && loadOf(item("e", ["light grey"])) === "light");
  check("compact spellings: offwhite, lightgrey, lightblue, darkgreen",
    loadOf(item("o", ["offwhite"])) === "white" && loadOf(item("lg", ["lightgrey"])) === "light"
    && loadOf(item("lb", ["lightblue"])) === "light" && loadOf(item("dg", ["darkgreen"])) === "dark");
  const ticks = [...$("splitBox").querySelectorAll("input[data-split]")].map(c => c.dataset.split);
  check("Settings offers all five splits", ticks.join() === "colour,fabric,weight,soil,kind", ticks);
  check("no fabric checkboxes on the loads while Fabric is not ticked",
    !$("loadList").querySelector('[data-f="fabric"]'));

  console.log("\n--- 2. ticking Fabric -------------------------------------------------");
  const tick = async id => { const c = $("splitBox").querySelector(`[data-split="${id}"]`);
    c.checked = !c.checked; c.dispatchEvent(new w.Event("change", {bubbles: true})); await drain(); };
  await tick("fabric");
  check("Fabric is now a split", ev("laundry.splits.includes('fabric')"));
  check("the loads show fabric conditions", !!$("loadList").querySelector('[data-f="fabric"]'));
  ev(`closet=[${JSON.stringify(item("silk1", ["white"], {fabric: "silk"}))}]`);
  await ev(`openSheet(closet[0],{isNew:false})`); await drain();
  check("the garment sheet shows Fabric", $("shFabricBox").style.display === "");
  check("…but not Weight or Dirt", $("shWeightBox").style.display === "none" && $("shSoilBox").style.display === "none");
  check("the fabric is shown", $("shFabric").value === "silk");
  ev("closeSheet()");

  console.log("\n--- 3. a Delicates load first ------------------------------------------");
  $("loadPreset").value = "delicates"; $("loadPreset").onchange();
  await $("loadPresetGo").onclick(); await drain();
  check("the preset puts Delicates on top", ev("laundry.loads[0].name") === "Delicates");
  check("a white silk blouse goes to Delicates", loadOf(item("s", ["white"], {fabric: "silk"})) === "delicate");
  check("a white cotton tee still goes to Whites", loadOf(item("t", ["white"], {fabric: "cotton"})) === "white");
  check("an unknown fabric is never assumed delicate", loadOf(item("u", ["white"])) === "white");
  await tick("fabric");
  check("unticking Fabric: the condition is ignored, not deleted",
    loadOf(item("s", ["white"], {fabric: "silk"})) === "white" && ev("laundry.loads[0].match.fabrics.length") === 4);
  await tick("fabric");

  ev(`laundry.splits=["colour","fabric","weight"]; laundry.loads=PRESETS.ldh.loads()`);
  check("with Lights as the catch-all, light grey still goes to Lights, not Darks",
    loadOf(item("lg", ["light grey"], {fabric: "cotton"})) === "light" && loadOf(item("g2", ["grey"])) === "dark");
  ev(`laundry.loads[3].match.fabrics=["silk"]`);
  check("a catch-all's leftover conditions do not stop its colours protecting shades",
    loadOf(item("lg2", ["light grey"], {fabric: "cotton"})) === "light");
  ev(`laundry.splits=["colour","fabric"]; laundry.loads=PRESETS.delicates.loads()`);

  console.log("\n--- 4. order matters; up and down -------------------------------------");
  const row = id => $("loadList").querySelector(`.loadRow[data-load="${id}"]`);
  row("white").querySelector('[data-f="up"]').click(); await drain();
  check("moving Whites up puts it above Delicates", ev("laundry.loads[0].id") === "white");
  check("…so a white silk blouse now goes with the whites", loadOf(item("s", ["white"], {fabric: "silk"})) === "white");
  row("white").querySelector('[data-f="down"]').click(); await drain();
  ev(`closet=[${JSON.stringify(item("c1", ["white"], {fabric: "cotton"}))}]`);
  await ev(`openSheet(closet[0],{isNew:false})`); await drain();
  check("the sheet's Automatic load starts as Whites", /Whites/.test($("shLoad").options[0].textContent));
  $("shFabric").value = "silk"; $("shFabric").dispatchEvent(new w.Event("change")); await drain();
  check("choosing silk updates it to Delicates before saving", /Delicates/.test($("shLoad").options[0].textContent),
    $("shLoad").options[0].textContent);
  ev("closeSheet()");

  console.log("\n--- 5. weight, dirt and kind need no field ----------------------------");
  ev(`laundry.splits=["weight","soil","kind"]; laundry.loads=cleanLoads([
    {id:"sport",name:"Sport",match:{soil:"heavy"}},
    {id:"heavy",name:"Heavy",match:{weight:"heavy"}},
    {id:"under",name:"Underwear",match:{kinds:["underwear"]}},
    {id:"rest",name:"Everything else",rest:true}])`);
  check("gym kit (active) is heavily soiled", loadOf(item("g", ["blue"], {formality: ["active"]})) === "sport");
  check("jeans are heavy", loadOf(item("j", ["blue"], {type: "jeans", group: "bottoms"})) === "heavy");
  check("a warmth-4 jumper is heavy", loadOf(item("k", ["red"], {type: "sweater", warmth: 4})) === "heavy");
  check("underwear by kind", loadOf(item("b", ["white"], {group: "underwear", type: "briefs"})) === "under");
  check("an old knitwear group reads as tops", ev(`kindOf({group:"knitwear"})`) === "tops");
  check("a per-garment choice beats the automatic weight",
    loadOf(item("j2", ["blue"], {type: "jeans", weight: "light"})) === "rest");
  ev(`closet=[${JSON.stringify(item("sw", ["red"], {type: "cardigan", warmth: 2}))}]`);
  await ev(`openSheet(closet[0],{isNew:false})`); await drain();
  check("a light cardigan opens as Everything else", /Everything else/.test($("shLoad").options[0].textContent),
    $("shLoad").options[0].textContent);
  $("shWarm").querySelector('[data-w="4"]').click(); await drain();
  check("re-graded to warmth 4 it reads Heavy, before saving", /Heavy/.test($("shLoad").options[0].textContent)
    && /heavy/.test($("shWeight").options[0].textContent), $("shLoad").options[0].textContent);
  ev("closeSheet()");
  ev(`closet=[${JSON.stringify(item("jn", ["blue"], {type: "jeans", group: "bottoms", category: "bottoms", roles: ["bottoms"], warmth: 1}))}]`);
  await ev(`openSheet(closet[0],{isNew:false})`); await drain();
  check("jeans open as Heavy", /Heavy/.test($("shLoad").options[0].textContent));
  $("shGroup").value = "tops"; $("shGroup").dispatchEvent(new w.Event("change")); await drain();
  check("moved to Tops, the kind is cleared and the preview follows", ev(`$("shType").value`) === ""
    && /Everything else/.test($("shLoad").options[0].textContent), [ev(`$("shType").value`), $("shLoad").options[0].textContent]);
  ev("closeSheet()");
  check("a load with no condition on a ticked split matches nothing",
    ev(`matchesLoad(${JSON.stringify(item("x", ["red"]))},{id:"z",match:{colors:["red"],fabrics:[],weight:"",soil:"",kinds:[]}})`) === false);

  ev(`laundry.splits=["colour","fabric"]; laundry.loads=cleanLoads([
    {id:"bs",name:"Black silk",match:{colors:["black"],fabrics:["silk"]}},
    {id:"dk",name:"Darks",match:{colors:["black"]}},
    {id:"r",name:"Rest",rest:true}])`);
  check("two loads sharing a colour: the other conditions decide",
    loadOf(item("bc", ["black"], {fabric: "cotton"})) === "dk" && loadOf(item("bs1", ["black"], {fabric: "silk"})) === "bs");

  ev(`laundry.loads=cleanLoads([
    {id:"nbs",name:"Navy silk",match:{colors:["navy blue"],fabrics:["silk"]}},
    {id:"dk",name:"Darks",match:{colors:["navy"]}},
    {id:"r",name:"Rest",rest:true}])`);
  check("a more specific load it fails does not block a broader one",
    loadOf(item("nb", ["navy blue"], {fabric: "cotton"})) === "dk" && loadOf(item("nb2", ["navy blue"], {fabric: "silk"})) === "nbs");

  console.log("\n--- 6. what was saved before ------------------------------------------");
  const old = ev(`JSON.stringify(cleanLoads([{id:"white",name:"Whites",colors:["white"]},{id:"dark",name:"Darks",colors:["navy"]},{id:"colorful",name:"Colourful",colors:[],rest:true}]))`);
  check("old loads with top-level colours migrate to colour conditions",
    JSON.parse(old)[1].match.colors.join() === "navy", old);
  check("junk splits fall back to Colour", ev(`cleanSplits(["nonsense"]).join()`) === "colour");
  ev(`laundry.splits=["colour"]; laundry.loads=COLOUR4()`);
  check("a hand-picked load still wins", loadOf(item("h", ["white"], {load: "dark"})) === "dark");
  ev(`closet=[${JSON.stringify(item("h", ["white"], {load: "dark"}))}]`); await ev("saveCloset()");
  check("…and Settings offers to let it follow the rules again", $("loadUnpin").style.display === "");
  await $("loadUnpin").onclick(); await drain();
  check("which clears it", ev("closet[0].load") === undefined && loadOf(ev("closet[0]")) === "white");

  console.log("\n--- 7. Laundry done with nothing waiting ------------------------------");
  ev("wearLog=[]");
  $("laundryBtn").onclick(); await drain();
  check("the picker opens anyway", $("washWrap").classList.contains("show"));
  check("and says how clothes get into the laundry", /Wearing it/.test($("washLoads").textContent));
  check("every load is listed", $("washLoads").querySelectorAll("input[data-load]").length === ev("laundry.loads.length"));

  console.log(`\n# ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
