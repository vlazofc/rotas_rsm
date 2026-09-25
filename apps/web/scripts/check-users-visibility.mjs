import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let usersStatus = 0;
  page.on("response", (response) => {
    if (new URL(response.url()).pathname === "/api/users") usersStatus = response.status();
  });

  await page.goto("http://127.0.0.1:8088/login", { waitUntil: "networkidle" });
  await page.locator('input[type="text"]').fill(process.env.SMOKE_ADMIN_EMAIL || "admin.local@example.com");
  await page.locator('input[type="password"]').fill(process.env.SMOKE_ADMIN_PASSWORD || "LocalAdminChangeMe123!");
  await page.getByRole("button", { name: /entrar/i }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 15_000 });
  await page.goto("http://127.0.0.1:8088/users", { waitUntil: "networkidle" });

  assert.equal(usersStatus, 200, "GET /api/users deve responder 200");
  const carrierTab = page.getByRole("button", { name: /Usuários de transportadoras/ });
  await carrierTab.click();
  await assert.doesNotReject(() => page.getByRole("cell", { name: "rene.souza.mendes@gmail.com" }).waitFor());
  assert.match(await carrierTab.innerText(), /1/, "A aba deve contabilizar o usuário da transportadora");

  const mastersTab = page.getByRole("button", { name: /Masters de transportadoras/ });
  await mastersTab.click();
  assert.ok((await page.locator("tbody tr").count()) >= 4, "A aba deve listar os masters existentes");

  await page.context().clearCookies();
  await page.goto("http://127.0.0.1:8088/login", { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.locator('input[type="text"]').fill("master.alfa@example.com");
  await page.locator('input[type="password"]').fill(process.env.SMOKE_ADMIN_PASSWORD || "LocalAdminChangeMe123!");
  await page.getByRole("button", { name: /entrar/i }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 15_000 });
  await page.goto("http://127.0.0.1:8088/users", { waitUntil: "networkidle" });
  const ownUsersTab = page.getByRole("button", { name: /Usuários da transportadora/ });
  assert.match(await ownUsersTab.innerText(), /1/, "O master deve ver o usuário da própria transportadora");
  await assert.doesNotReject(() => page.getByRole("cell", { name: "rene.souza.mendes@gmail.com" }).waitFor());
  assert.equal(await page.getByText("master.beta@example.com").count(), 0, "O master não pode ver usuários de outra transportadora");
  console.log("PASS: usuários visíveis para Adimax e para o master da própria transportadora");
} finally {
  await browser.close();
}
