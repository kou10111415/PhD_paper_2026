import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const base=process.env.VIEWER_BASE_URL||'http://127.0.0.1:8765';
const browser=await chromium.launch({headless:true,channel:'chrome'});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const errors=[],checks=[];
context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));
const page=await context.newPage();
try {
  for(const [plan,count] of [['env6th',2298],['ene7th',5094]]) {
    await page.goto(`${base}/viewers/${plan}/judgments.html`);
    await page.waitForFunction(()=>window.judgmentViewer);
    assert.equal(await page.evaluate(()=>judgmentViewer.all.length),count);
    assert.equal(await page.locator('.card').count(),20);
    const sample=await page.evaluate(()=>{
      const r=judgmentViewer.all.find(r=>r.source_ref&&(r.matched_revisions||[]).some(v=>v.new_ref?.quotes.length));
      return {id:r.request_id,ref:r.matched_revisions.find(v=>v.new_ref?.quotes.length).new_ref};
    });
    await page.locator('#search').fill(sample.id);
    assert.equal(await page.locator('.card').count(),1);
    await page.getByRole('button',{name:'議事録・原資料を表示',exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector('.source-pane').hidden);
    let reader=page.frameLocator('iframe');
    await reader.locator('.target').first().waitFor();
    assert.equal(await reader.locator('.target').count(),1);
    await page.getByRole('button',{name:'閉じる',exact:true}).click();
    assert.equal(await page.locator('.source-pane').isVisible(),false);
    // Follow the actual separate-tab link, preserving IDs and quotations.
    const separate=page.locator('.card .ref-actions a[target="_blank"]').first();
    const [popup]=await Promise.all([page.waitForEvent('popup'),separate.click()]);
    await popup.waitForFunction(()=>window.readerResult);
    assert.ok((await popup.evaluate(()=>readerResult)).found>0);
    await popup.close();
    const label=await page.locator('button[data-source-ref]').allTextContents();
    const targetButton=page.getByRole('button',{name:label.find(s=>s==='新版の本文を表示'||s==='本文を表示'),exact:true}).first();
    await targetButton.click();
    await reader.locator('.target').first().waitFor();
    await page.screenshot({path:path.join(root,`verification-${plan}-panel.png`),fullPage:false});
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.source-pane').isVisible(),false);
    const readerPage=await context.newPage();
    const u=new URL(sample.ref.url,`${base}/viewers/${plan}/judgments.html`);
    const params=new URLSearchParams();sample.ref.ids.forEach(id=>params.append('id',id));sample.ref.quotes.forEach(q=>params.append('q',q));u.hash=params.toString();
    await readerPage.goto(u.href);await readerPage.waitForFunction(()=>window.readerResult);
    const result=await readerPage.evaluate(()=>readerResult);
    assert.equal(result.found,sample.ref.ids.length);assert.equal(result.missing.length,0);assert.ok(result.highlights>0);
    // Hash navigation in the same document must update the target and clear marks.
    const other=await readerPage.locator('.source-block:not(.target)').first().getAttribute('id');
    await readerPage.evaluate(id=>{location.hash=new URLSearchParams({id}).toString();},other);
    await readerPage.waitForFunction(id=>window.readerResult.ids[0]===id,other);
    assert.equal(await readerPage.locator('mark').count(),0);
    assert.equal(await readerPage.locator('.target').getAttribute('id'),other);
    await readerPage.close();
    if(plan==='env6th') {
      await page.locator('#search').fill('');
      await page.locator('#judgment').selectOption({label:'未判定'});
      assert.equal(await page.evaluate(()=>judgmentViewer.filtered().length),87);
      assert.ok((await page.locator('#cards').textContent()).includes('保存済みの判定結果がありません'));
      await page.locator('#judgment').selectOption('');
      const provisional=await page.evaluate(()=>judgmentViewer.all.find(r=>r.human_review_provisional).request_id);
      await page.locator('#search').fill(provisional);
      assert.ok((await page.locator('#cards').textContent()).includes('人手確認（暫定）'));
    }
    await page.setViewportSize({width:390,height:844});
    await page.locator('#search').fill(sample.id);
    await page.getByRole('button',{name:'議事録・原資料を表示',exact:true}).click();
    assert.equal(await page.locator('.source-pane').evaluate(e=>Math.round(e.getBoundingClientRect().width)),390);
    await page.getByRole('button',{name:'閉じる',exact:true}).click();
    await page.setViewportSize({width:1440,height:1000});
    if(plan==='env6th')await page.screenshot({path:path.join(root,'verification-judgments.png'),fullPage:false});
    checks.push(`${plan}: rows, filters, source panel, close/Escape, reader highlight, hash navigation, mobile`);
  }
  // Check multiple paragraph targets and a footnote and heading on each plan.
  for(const plan of ['env6th','ene7th']) {
    await page.goto(`${base}/viewers/${plan}/judgments.html`);
    const refs=await page.evaluate(()=>judgmentViewer.all.flatMap(r=>(r.matched_revisions||[]).flatMap(v=>[v.old_ref,v.new_ref]).filter(Boolean)));
    for(const kind of ['multi','note','head']) {
      const ref=refs.find(r=>kind==='multi'?r.ids.length>1:r.ids.some(id=>id.startsWith(kind)));
      if(!ref)continue;
      const u=new URL(ref.url,`${base}/viewers/${plan}/judgments.html`),params=new URLSearchParams();
      ref.ids.forEach(id=>params.append('id',id));(ref.quotes||[]).forEach(q=>params.append('q',q));u.hash=params.toString();
      const p=await context.newPage();await p.goto(u.href);await p.waitForFunction(()=>window.readerResult);
      assert.equal((await p.evaluate(()=>readerResult)).found,ref.ids.length);await p.close();
      checks.push(`${plan}: ${kind} reader targets`);
    }
    await page.goto(`${base}/viewers/${plan}/clustering.html`,{waitUntil:'networkidle'});
    await page.waitForFunction(()=>window.Plotly&&document.querySelector('#scatter').data?.length,{timeout:30000});
    const info=await page.evaluate(()=>{
      const plot=document.getElementById('scatter'),trace=plot.data.find(t=>t.customdata.some(r=>r[0]==='分科会'||r[0]==='部会'||r[0]==='総会'));
      const index=trace.customdata.findIndex(r=>r[0]==='分科会'||r[0]==='部会'||r[0]==='総会');
      plot.emit('plotly_click',{points:[{data:trace,pointIndex:index}]});
      return document.querySelector('.cluster-request').textContent;
    });
    assert.ok(info.includes('この要求の改訂判定を開く'));
    await page.getByRole('button',{name:'議事録・原資料を表示',exact:true}).click();
    await page.frameLocator('iframe').locator('.target').waitFor();
    await page.getByRole('button',{name:'閉じる',exact:true}).click();
    checks.push(`${plan}: Plotly point → source panel and judgment deep link`);
  }
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(root,'verification-browser.json'),JSON.stringify({base,checks,errors},null,2)+'\n');
  console.log(JSON.stringify({checks,errors},null,2));
} finally {await browser.close();}
