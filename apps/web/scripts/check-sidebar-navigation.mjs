import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from 'playwright-core';
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),server:{host:'127.0.0.1',port:0}});
let browser;
try {
 await server.listen();
 browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:800}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.setItem('access_token','test-token'));
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname;
  const data=path==='/api/auth/me'?{id:1,name:'Teste',email:'test@example.com',role:'admin_global',permissions:[],must_change_password:false}:path==='/api/branding'?{}:path==='/api/tenants/me'?{feature_financeiro:true,feature_rastreamento:true}:[];
  return route.fulfill({json:data});
 });
 await page.goto(server.resolvedUrls.local[0]+'purchases');
 const nav=page.locator('.sidebar .nav-groups');
 await nav.waitFor();
 await page.locator('.sidebar a[href="/financial-accounts?type=payable"]').scrollIntoViewIfNeeded();
 await nav.evaluate(n=>{window.__originalNav=n;});
 for(const target of ['/financial-accounts?type=payable','/financial-accounts?type=receivable','/purchases']){
  const link=page.locator(`.sidebar a[href="${target}"]`);
  await link.scrollIntoViewIfNeeded();
  const before=await nav.evaluate(n=>n.scrollTop);
  assert(before>0,'Menu must be scrolled for this regression check');
  await link.click();
  await page.waitForURL(url=>url.pathname+url.search===target);
  await page.locator('main h2').first().waitFor();
  assert(await nav.evaluate(n=>n===window.__originalNav),'Navigation was remounted');
  assert(Math.abs(await nav.evaluate(n=>n.scrollTop)-before)<2,'Sidebar scroll position changed');
  console.log('PASS sidebar position retained: '+target);
 }
 await page.goBack();
 assert(await nav.evaluate(n=>n===window.__originalNav),'Back navigation remounted sidebar');
 assert.deepEqual(errors,[]);
} finally {await browser?.close();await server.close();}
