import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const requireFromWeb = createRequire(new URL("../apps/web/package.json", import.meta.url));
const { chromium } = requireFromWeb("playwright-core");

const root = path.resolve(import.meta.dirname, "..");
const envText = fs.readFileSync(path.join(root, ".env"), "utf8");
const env = Object.fromEntries(envText.split(/\r?\n/).filter((line) => line && !line.startsWith("#") && line.includes("=")).map((line) => {
  const at = line.indexOf("=");
  return [line.slice(0, at).trim(), line.slice(at + 1).trim().replace(/^['"]|['"]$/g, "")];
}));
const base = "http://localhost:8089";
const body = new URLSearchParams({ username: env.SEED_ADMIN_EMAIL, password: env.SEED_ADMIN_PASSWORD });
const login = await fetch(`${base}/api/auth/login`, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body });
if (!login.ok) throw new Error(`Login de demonstração falhou: ${login.status}`);
const tokens = await login.json();
const out = path.join(root, "docs", "assets", "demo");
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await page.addInitScript(({ access, refresh }) => { localStorage.setItem("access_token", access); localStorage.setItem("refresh_token", refresh); }, { access: tokens.access_token, refresh: tokens.refresh_token });
const screens = [
  ["dashboard", "/"], ["monitoramento-gps", "/tracking"], ["rotas", "/routes"],
  ["frota-manutencao", "/fleet-maintenance?tab=orders"], ["dashboard-financeiro", "/financial-dashboard"],
  ["relatorios", "/reports"], ["auditoria", "/audit"],
];
for (const [name, route] of screens) {
  await page.goto(`${base}${route}`, { waitUntil: "networkidle", timeout: 30000 });
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: false });
}
await browser.close();
console.log(`${screens.length} telas capturadas em ${out}`);
