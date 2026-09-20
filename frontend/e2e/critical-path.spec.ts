import { expect, test } from "@playwright/test";

/**
 * The critical path from the architecture doc's own Phase F exit criterion:
 * register → organization → project → database list, entirely through the
 * dashboard, never calling the API directly (cf.
 * docs/architecture/09-plan-de-phases.md's Phase F section).
 */
test("register, create an organization, create a project, see its empty database list", async ({
  page,
}) => {
  const unique = Date.now();
  const email = `e2e-${unique}@example.com`;

  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();

  // A brand-new user has no organizations yet.
  await expect(page).toHaveURL(/\/dashboard\/organizations\/new/);

  await page.getByLabel("Name").fill("E2E Test Org");
  await page.getByLabel("Slug").fill(`e2e-org-${unique}`);
  await page.getByRole("button", { name: "Create organization" }).click();

  await expect(page).toHaveURL(/\/dashboard\/[^/]+\/projects$/);
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

  await page.getByLabel("Name").fill("E2E Project");
  await page.getByLabel("Slug").fill("e2e-project");
  await page.getByRole("button", { name: "New project" }).click();

  await expect(page.getByText("E2E Project")).toBeVisible();
  await page.getByText("E2E Project").click();

  await expect(page).toHaveURL(/\/databases$/);
  await expect(page.getByRole("heading", { name: "Databases" })).toBeVisible();
  await expect(page.getByText("No databases yet")).toBeVisible();
});

test("logging out then back in reaches the dashboard again", async ({ page }) => {
  const unique = Date.now();
  const email = `e2e-relogin-${unique}@example.com`;
  const password = "correct-horse-battery-staple";

  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
});

test("visiting /dashboard while logged out redirects to /login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
