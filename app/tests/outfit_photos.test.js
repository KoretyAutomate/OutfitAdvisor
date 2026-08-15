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

  console.log("\n--- 3. removing a worn photo waits for Save ----------------------");
  // Regression, 2026-08-14 (found by the pre-push reviewer): the remove button
  // deleted the file and persisted wornPhoto=false immediately, so dismissing
  // the sheet — which discards every other edit — destroyed the photo anyway.
  ev(`closet=[{id:"q1",label:"navy polo",category:"base",group:"tops",type:"polo",
       roles:["base"],count:1,colors:[],warmth:2,formality:["smart"],waterproof:false,
       photo:true,wornPhoto:true}];
      localStorage.setItem("oa.photo.q1-worn","KEEPME");
      openSheet(closet[0],{});`);
  for (let i = 0; i < 10; i++) await drain();

  ev(`$("shWornDel").click()`);
  for (let i = 0; i < 10; i++) await drain();
  check("the photo disappears from the sheet at once",
    w.document.getElementById("shWornImg").style.display === "none");
  check("but the file is still on disk — nothing is committed yet",
    w.localStorage.getItem("oa.photo.q1-worn") === "KEEPME");
  check("and the closet still says the item has one",
    ev(`closet[0].wornPhoto`) === true);

  ev(`$("shCancel").click()`);
  for (let i = 0; i < 10; i++) await drain();
  check("cancelling the sheet keeps the photo — the whole point",
    w.localStorage.getItem("oa.photo.q1-worn") === "KEEPME");
  check("and leaves the closet untouched", ev(`closet[0].wornPhoto`) === true);

  ev(`openSheet(closet[0],{}); `);
  for (let i = 0; i < 10; i++) await drain();
  ev(`$("shWornDel").click()`);
  for (let i = 0; i < 10; i++) await drain();
  ev(`$("shSave").click()`);
  for (let i = 0; i < 10; i++) await drain();
  check("saving after a removal DOES delete the file",
    w.localStorage.getItem("oa.photo.q1-worn") === null);
  check("and records that the item no longer has one",
    ev(`closet[0].wornPhoto`) === false);

  console.log("\n--- 4. a slow photo load cannot land on a newer outfit ------------");
  // Regression, 2026-08-14 (found by the pre-push reviewer): photoLoad() is a
  // filesystem read that renderOutfit deliberately does not wait for. Render a
  // second outfit while the first one's reads are in flight and the late arrival
  // pasted an old pick's picture onto the new list.
  ev(`closet=[{id:"r1",label:"old coat",category:"outer",group:"outerwear",type:"coat",
       roles:["outer"],count:1,colors:[],warmth:5,formality:["smart"],waterproof:false,
       photo:true,wornPhoto:false}];
      localStorage.setItem("oa.photo.r1","STALEPIC");
      document.getElementById("outfitList").innerHTML='<li data-slot="outer"><span class="ic">x</span></li>';`);
  const li = () => w.document.querySelector('#outfitList li[data-slot="outer"]');

  // Paint with the CURRENT generation, then bump it mid-flight, as a second
  // render would. The picture must never be inserted.
  ev(`(async()=>{ const g=outfitGen; const p=paintLinePhoto(
        document.querySelector('#outfitList li[data-slot="outer"]'),"r1",g);
      outfitGen++; await p; })()`);
  for (let i = 0; i < 10; i++) await drain();
  check("a photo from the previous outfit is dropped, not inserted",
    !li().querySelector("img.pic"));

  // Same call with a generation that is still current must still paint.
  ev(`paintLinePhoto(document.querySelector('#outfitList li[data-slot="outer"]'),"r1",outfitGen)`);
  for (let i = 0; i < 10; i++) await drain();
  check("while a current one still paints", !!li().querySelector("img.pic"));

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
