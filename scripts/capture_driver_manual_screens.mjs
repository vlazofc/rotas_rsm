import playwright from "../apps/web/node_modules/playwright-core/index.js";
import fs from "node:fs";
import path from "node:path";

const { chromium } = playwright;
const root = path.resolve(path.dirname(decodeURIComponent(new URL(import.meta.url).pathname).replace(/^\/(.:)/, "$1")), "..");
const out = path.join(root, "docs", "manual", "assets");
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const page = await browser.newPage({ viewport: { width: 430, height: 900 }, deviceScaleFactor: 1.5, userAgent: "Mozilla/5.0 Android AdimaxMotorista/1.3 AndroidWebView" });
await page.goto("http://127.0.0.1:5173/login", { waitUntil: "networkidle" });
await page.screenshot({ path: path.join(out, "motorista-login.png"), fullPage: true });
await page.evaluate(() => localStorage.setItem("access_token", "manual-demonstracao"));

const routeDemo = { id:101,branch_id:1,codigo_ut:"ROTA DEMONSTRAÇÃO",route_date:"2026-09-15",origin_name:"CD Piedade",origin_address:"Piedade - SP",driver_id:10,vehicle_id:20,status:"em_rota",source:"manual",vehicle_requested:"Caminhão",vehicle_sent:"Caminhão",helper_assigned:false,tracked:true,actual_departure_at:"2026-09-15T11:00:00Z",closed_at:null,dock_session:{arrival_cd_at:"2026-09-15T10:15:00Z",operator_released_at:"2026-09-15T11:00:00Z",departure_cd_at:"2026-09-15T11:00:00Z",loading_minutes:45},stops:[{id:1001,sequence:1,customer_name:"Cliente Exemplo",customer_address:"Avenida Principal, 100",city:"Sorocaba",status:"em_rota",planned_date:"2026-09-15",planned_time:"14:00",weight_kg:850,pallets:2,order_number:"PED-1001",checkin_at:"2026-09-15T13:40:00Z",operations:[]}],events:[] };

await page.route("http://127.0.0.1:8001/**", async r => {
  const u = new URL(r.request().url());
  let body = [];
  if (u.pathname === "/auth/me") body={id:10,email:"motorista@exemplo.com",name:"Motorista Demonstração",role:"motorista",branch_id:1,tenant_id:1,permissions:["module.routes","module.occurrences","module.tracking"],navigation_layout:"sidebar",must_change_password:false};
  else if (u.pathname === "/tenants/me") body={feature_rastreamento:true,feature_route_optimization:true,feature_km_calculation:true};
  else if (u.pathname === "/tracking/app-permission-consent") body={accepted:true};
  else if (u.pathname === "/routes") body=[routeDemo];
  else if (u.pathname === "/routes/101") body=routeDemo;
  else if (u.pathname === "/drivers") body=[{id:10,name:"Motorista Demonstração",active:true}];
  else if (u.pathname === "/vehicles") body=[{id:20,plate:"ABC1D23",active:true}];
  else if (u.pathname.includes("failure-reasons")) body=[{id:1,code:"cliente_fechado",label:"Cliente fechado",active:true}];
  else if (u.pathname.includes("occurrence-categories")) body=[{id:1,code:"atraso",name:"Atraso",active:true},{id:2,code:"avaria",name:"Avaria",active:true},{id:3,code:"outros",name:"Outros",active:true}];
  else if (u.pathname === "/erp/occurrences") body=[{id:1,route_id:101,codigo_ut:"ROTA DEMONSTRAÇÃO",plate:"ABC1D23",driver:"Motorista Demonstração",category:"atraso",severity:"media",description:"Trânsito intenso no acesso ao cliente.",status:"aberta",created_at:"2026-09-15T13:10:00Z"}];
  else if (u.pathname === "/notifications/live" || u.pathname === "/notifications") body=[];
  else if (u.pathname === "/branding/public") body={};
  await r.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
});

for (const [url,name] of [["/routes","motorista-rotas.png"],["/routes/101","motorista-detalhe-rota.png"],["/occurrences","motorista-ocorrencias.png"]]) {
  await page.goto(`http://127.0.0.1:5173${url}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(out, name), fullPage: true });
}
await page.goto("http://127.0.0.1:5173/routes", { waitUntil: "networkidle" });
await page.getByRole("button", { name: /^entregar$/i }).first().click();
await page.waitForTimeout(250);
await page.screenshot({ path: path.join(out, "motorista-entrega.png"), fullPage: true });
await page.getByRole("button", { name: /cancelar/i }).first().click();
await page.getByRole("button", { name: /^recusado$/i }).first().click();
await page.waitForTimeout(250);
await page.screenshot({ path: path.join(out, "motorista-recusado.png"), fullPage: true });
await page.goto("http://127.0.0.1:5173/occurrences", { waitUntil: "networkidle" });
const newOccurrence = page.getByRole("button", { name: /nova ocorrência/i }).first();
if (await newOccurrence.count()) {
  await newOccurrence.click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(out, "motorista-nova-ocorrencia.png"), fullPage: true });
}
await browser.close();
console.log("Capturas demonstrativas concluídas em", out);
