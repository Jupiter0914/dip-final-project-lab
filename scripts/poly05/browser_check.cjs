
/* Open the actual file:// pages in an offline Chromium browser and exercise the saved runs. */
const fs = require("node:fs");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const assert = require("node:assert/strict");
const {chromium} = require("playwright");

async function platformFonts(page, selectors) {
  const session = await page.context().newCDPSession(page);
  await session.send("DOM.enable");
  await session.send("CSS.enable");
  const {root} = await session.send("DOM.getDocument");
  const result = {};
  for (const selector of selectors) {
    const {nodeId} = await session.send("DOM.querySelector", {nodeId: root.nodeId, selector});
    const {fonts} = await session.send("CSS.getPlatformFontsForNode", {nodeId});
    result[selector] = fonts.filter(f => f.glyphCount).map(f => f.familyName);
  }
  await session.detach();
  return result;
}

async function main() {
  const root = path.resolve(__dirname, "../..");
  const dir = path.join(root, "report/poly05");
  const dest = process.argv[2] ? path.resolve(process.argv[2]) : null;
  if (dest) fs.mkdirSync(dest, {recursive:true});
  const data = JSON.parse(fs.readFileSync(path.join(dir, "replay/index.json"), "utf8"));
  const browser = await chromium.launch({
    headless:true,
    ...(process.env.POLY05_CHROMIUM ? {executablePath:process.env.POLY05_CHROMIUM} : {})
  });
  try {
    const context = await browser.newContext({offline:true, viewport:{width:1220,height:920}});
    const page = await context.newPage();
    const problems = [];
    page.on("pageerror", e => problems.push(e.message));
    page.on("request", r => {if (/^https?:/.test(r.url())) problems.push(r.url());});
    page.on("requestfailed", r => problems.push(r.url()+" "+r.failure()?.errorText));
    await page.goto(pathToFileURL(path.join(dir, "replay/index.html")).href);
    await page.waitForFunction(() => document.querySelectorAll("canvas[data-drawn]").length===3);
    const fonts = await platformFonts(page, ["#identity", "h1", "#average"]);
    const allFonts = Object.values(fonts).flat().join(" ");
    assert.match(allFonts,/Times New Roman/i);
    assert.match(allFonts,/SimSun|宋体/i);
    const results = [];
    let modes=0;
    for (let i=0; i<data.cases.length; i++) {
      const c=data.cases[i];
      await page.selectOption("#case",String(i));
      assert.equal(await page.locator("#identity").textContent(),c.dataset+" · "+c.id);
      assert.equal(Number(await page.locator("#average").textContent()),Number(c.source_mean.toFixed(3)));
      assert.equal(Number(await page.locator("#delta").textContent()),c.repeat_delta);
      const displayed=await page.locator("#metrics tr").evaluateAll(rs=>rs.map(r=>Array.from(r.cells,c=>c.textContent)));
      for (const [j,m] of ["within_full","cross"].entries()) {
        const q=c.methods[m];
        for (const [k,f] of [[0,"size"],[1,"round"],[2,"fp"],[3,"fn"],[4,"xor"],[6,"serialized_ms"],[7,"delivered_ms"],[8,"search_end_ms"],[9,"end_ms"]]) {
          assert.equal(Number(displayed[k][j+1]),Number(q[f].toFixed(4)));
        }
        assert.equal(Number(displayed[5][j+1]),Number(q.iou.toFixed(6)));
        assert.ok((await page.locator("#s"+(j+1)).textContent()).includes(q.ring_points.join(" / ")));
      }
      for (const view of ["full","crop"]) {
        for (const mode of ["mask","errors"]) {
          await page.locator('[data-view="'+view+'"]').click();
          await page.locator('[data-mode="'+mode+'"]').click();
          await page.waitForFunction(({id,full,width})=>Array.from(document.querySelectorAll("canvas")).every(c=>c.dataset.drawn?.includes(id)&&c.width===width),
              {id:c.id,full:view==="full",width:view==="full"?c.width:c.crop[2]});
          assert.equal(await page.locator(".error-key").first().isVisible(), mode==="errors");
          modes++;
        }
      }
      const links=await page.locator("#files a").evaluateAll(ns=>ns.map(a=>a.getAttribute("href")));
      for (const p of links) assert.ok(fs.statSync(path.resolve(dir,"replay",p)).size>0);
      if (c.id===data.action.id) {
        await page.locator("#action summary").click();
        assert.equal(await page.locator("#action img").evaluate(im=>im.complete && im.naturalWidth>100),true);
        assert.equal(await page.locator("#action-files a").count(),2);
      }
      results.push(c.id);
    }
    await page.selectOption("#case","0");
    await page.locator("#next").click();await page.locator("#prev").click();
    assert.equal(await page.locator("#case").inputValue(),"0");
    await page.locator('[data-view="full"]').click();
    await page.waitForFunction(()=>document.querySelectorAll("canvas[data-drawn]").length===3);
    if(dest) await page.screenshot({path:path.join(dest,"replay-desktop.png"),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    if(dest) await page.screenshot({path:path.join(dest,"replay-mobile.png"),fullPage:true});
    await page.setViewportSize({width:1220,height:920});
    await page.goto(pathToFileURL(path.join(dir,"manuscript_materials.html")).href);
    await page.waitForFunction(()=>[...document.images].length===8&&[...document.images].every(im=>im.complete&&im.naturalWidth>0));
    assert.equal(await page.locator("table").count(),4);
    assert.equal(await page.locator("img.formula").count(),2);
    const tableFonts=await platformFonts(page,["tbody tr:first-child td:first-child","h1"]);
    assert.match(Object.values(tableFonts).flat().join(" "),/Times New Roman/i);
    assert.match(Object.values(tableFonts).flat().join(" "),/SimSun|宋体/i);
    if(dest) await page.screenshot({path:path.join(dest,"reader.png")});
    assert.deepEqual(problems,[]);
    console.log(JSON.stringify({browser:browser.version(),scheme:"file",network:"offline",cases:results,
      view_mode_checks:modes,figures:6,formula_images:2,reader_tables:4,
      replay_platform_fonts:fonts,reader_platform_fonts:tableFonts,mobile_overflow:false,errors:problems},null,2));
  } finally {await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
