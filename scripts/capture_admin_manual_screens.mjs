import playwright from "../apps/web/node_modules/playwright-core/index.js";
import fs from "node:fs";
import path from "node:path";

const { chromium } = playwright;
const root = path.resolve(path.dirname(decodeURIComponent(new URL(import.meta.url).pathname).replace(/^\/(.:)/, "$1")), "..");
const out = path.join(root, "docs", "manual", "assets");
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
await page.goto("http://127.0.0.1:8088/login", { waitUntil: "networkidle" });
await page.screenshot({ path: path.join(out, "login.png"), fullPage: true });
await page.locator('input[type="text"]').fill("admin.local@example.com");
await page.locator('input[type="password"]').fill("LocalAdminChangeMe123!");
await page.getByRole("button", { name: /entrar/i }).click();
await page.waitForURL(url => !url.pathname.endsWith("/login"), { timeout: 15000 });

const screens = [
  ["/", "dashboard.png"],
  ["/routes", "routes.png"],
  ["/routing", "routing.png"],
  ["/routing/manual", "manual-routing.png"],
  ["/occurrences", "occurrences.png"],
  ["/gallery", "gallery.png"],
  ["/tracking", "tracking.png"],
  ["/config/drivers", "drivers.png"],
  ["/config/vehicles", "vehicles.png"],
  ["/reports", "reports.png"],
  ["/users", "users.png"],
  ["/profiles", "profiles.png"],
];

for (const [url, name] of screens) {
  await page.goto(`http://127.0.0.1:8088${url}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(out, name), fullPage: true });
}

await page.goto("http://127.0.0.1:8088/routes", { waitUntil: "networkidle" });
const routeLink = page.locator('button.route-code').first();
if (await routeLink.count()) {
  await routeLink.click();
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: path.join(out, "route-detail.png"), fullPage: true });
}

await browser.close();
console.log("Capturas administrativas concluídas em", out);
