import { expect, test } from "@playwright/test";

test("creating a database with a valid lowercase name succeeds", async ({ page }) => {
  const unique = Date.now();
  const email = `e2e-createdb-${unique}@example.com`;

  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard\/organizations\/new/, { timeout: 60_000 });

  await page.getByLabel("Name").fill("Create DB Org");
  await page.getByLabel("Slug").fill(`create-db-org-${unique}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard\/[^/]+\/projects$/);

  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill("BUSINESS");
  await page.getByLabel("Slug").fill("business");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("link", { name: "BUSINESS" }).click();
  await expect(page).toHaveURL(/databases$/);

  await page.getByRole("button", { name: "New database" }).click();
  // Same scenario the user hit: typing an uppercase name should be rejected
  // client-side (native pattern validation), not sent to the backend at all.
  await page.getByPlaceholder("my-database").fill("BUSINESS");
  const nameInput = page.getByPlaceholder("my-database");
  await expect(nameInput).toHaveJSProperty("validity.valid", false);

  await nameInput.fill("business-db");
  await page.getByRole("button", { name: "Create database" }).click();
  await expect(page.getByText("business-db")).toBeVisible({ timeout: 15_000 });
});
