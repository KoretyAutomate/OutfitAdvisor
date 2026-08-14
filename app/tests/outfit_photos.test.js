/**
 * outfit_photos.test.js — the advice shows the clothes themselves (user, 2026-08-14).
 *
 * Loads the REAL app/www/index.html in jsdom, same discipline as the other suites.
 *
 * "Recommendations must include pictures from the closet, and those pictures must
 * show the image when it's wearing." Both halves fail INVISIBLY: a missing picture
 * still leaves a line that reads perfectly well, it just quietly stops being the
 * feature that was asked for, and a flat photo shown where a worn one exists is
 * indistinguishable from having no worn photo at all.
 *
 * photoLoad() falls back to localStorage outside the native app, so the tests seed
 * that and exercise the real lookup rather than a stub of it.
 *
 * Run: NODE_PATH=<...>/node_modules node tests/outfit_photos.test.js
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

const dom = new JSDOM(fs.readFileSync(HTML, "utf8"), {
  runScripts: "dangerously", url: "https://localhost/", pretendToBeVisual: true,
});
const w = dom.window;
const ev = (c) => w.eval(c);
const drain = () => new Promise(r => setTimeout(r, 0));

(async () => {
  for (let i = 0; i < 20 && !ev("state.baseUrl"); i++) await drain();
  await new Promise(r => setTimeout(r, 30));   // let load()'s last await settle

  console.log("\n--- 1. the recommendation shows the clothes themselves ------------");


  ev(`closet=[
    {id:"p1",label:"navy polo",category:"base",group:"tops",type:"polo",roles:["base"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false,photo:true,wornPhoto:true},
    {id:"p2",label:"wool coat",category:"outer",group:"outerwear",type:"coat",roles:["outer"],count:1,colors:[],warmth:5,formality:["smart"],waterproof:false,photo:true,wornPhoto:false},
    {id:"p3",label:"dark chinos",category:"bottoms",group:"bottoms",type:"trousers",roles:["bottoms"],count:1,colors:[],warmth:3,formality:["casual"],waterproof:false,photo:false,wornPhoto:false}
  ]; wearLog=[];
    localStorage.setItem("oa.photo.p1","FLATPOLO");
    localStorage.setItem("oa.photo.p1-worn","WORNPOLO");
    localStorage.setItem("oa.photo.p2","FLATCOAT");`);

  const OUTFIT = { inner: "generic vest", base: "navy polo", mid: "None needed",
    outer: "wool coat", bottoms: "dark chinos", footwear: "Sneakers", accessories: "None" };
  const RES = { closetUsed: true, closetSent: true,
    picks: { inner: null, base: "p1", mid: null, outer: "p2", bottoms: "p3",
             footwear: null, accessories: null } };
  ev(`renderOutfit(${JSON.stringify(OUTFIT)}, "text", "llm", ${JSON.stringify(RES)})`);
  for (let i = 0; i < 10; i++) await drain();     // photo lookups are async

  const pic = slot => w.document.querySelector(`#outfitList li[data-slot="${slot}"] img.pic`);
  check("a picked item shows a picture from the closet", !!pic("base"));
  check("and it is the WORN photo when there is one",
    pic("base").src.endsWith("WORNPOLO"), pic("base") && pic("base").src);
  check("the worn picture is not marked as a flat one",
    !pic("base").classList.contains("flat"));
  check("an item with only a flat photo still shows it",
    !!pic("outer") && pic("outer").src.endsWith("FLATCOAT"));
  check("and it is marked flat, so the user knows to add a worn shot",
    pic("outer").classList.contains("flat"));
  check("the emoji stand-in gives way to the real picture",
    w.document.querySelector('#outfitList li[data-slot="base"] .ic').style.display === "none");
  check("an item with no photo at all shows none", !pic("bottoms"));
  check("a generic line has no picture — there is no item to photograph", !pic("inner"));
  check("the picture count matches the picks that HAVE photos",
    w.document.querySelectorAll("#outfitList img.pic").length === 2,
    w.document.querySelectorAll("#outfitList img.pic").length);

  console.log("\n--- 2. deleting an item takes BOTH of its pictures ----------------");
  ev(`sheet={item:closet.find(i=>i.id==="p1"),isNew:false,b64:null,wornB64:null};`);
  ev(`$("shDel").click()`);
  for (let i = 0; i < 10; i++) await drain();
  check("the flat photo is gone", w.localStorage.getItem("oa.photo.p1") === null);
  check("the worn photo is gone too — otherwise it leaks forever",
    w.localStorage.getItem("oa.photo.p1-worn") === null);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
