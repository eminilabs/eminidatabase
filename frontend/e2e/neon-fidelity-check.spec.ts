import { expect, test } from "@playwright/test";

test("neon fidelity visual check", async ({ page }) => {
  const unique = Date.now();
  const email = `fidelitycheck-${unique}@example.com`;

  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/organizations\/new/, { timeout: 60_000 });

  await page.getByLabel("Name").fill("Emini");
  await page.getByLabel("Slug").fill(`emini-${unique}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/projects$/);
  await expect(page.locator("header").getByText("Emini", { exact: true })).toBeVisible({ timeout: 5000 });
  await page.screenshot({ path: "fidelity-01-projects-empty.png", fullPage: true });

  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill("Business");
  await page.getByLabel("Slug").fill("business");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "fidelity-02-projects-list.png", fullPage: true });

  await page.getByRole("link", { name: "Business" }).click();
  await expect(page).toHaveURL(/databases$/);
  await page.screenshot({ path: "fidelity-03-databases-empty.png", fullPage: true });

  await page.getByRole("button", { name: "New database" }).click();
  await page.getByPlaceholder("my-database").fill("main-db");
  await page.getByRole("button", { name: "Create database" }).click();
  await expect(page.getByText("main-db")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: "fidelity-04-databases-list.png", fullPage: true });
});
