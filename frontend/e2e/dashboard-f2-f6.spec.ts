import { expect, test } from "@playwright/test";

/**
 * Covers the F.2–F.6 additions reachable without a real Data Plane Agent/node
 * (API keys, webhooks, members, billing page, database detail shell). SQL
 * Editor, extensions, roles, backups/restore, and payment settlement all
 * require a database that actually reaches `running`, which needs a real
 * registered node + agent — a heavier live-infra setup not exercised here.
 * Documented limitation, not skipped silently (same reasoning as the OAuth
 * consent screen / FedaPay approval limitations noted elsewhere).
 */

async function registerAndCreateOrg(page: import("@playwright/test").Page, unique: number) {
  const email = `e2e-f2f6-${unique}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard\/organizations\/new/);

  await page.getByLabel("Name").fill("F2F6 Org");
  await page.getByLabel("Slug").fill(`f2f6-org-${unique}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard\/[^/]+\/projects$/);

  return page.url().match(/\/dashboard\/([^/]+)\/projects/)![1];
}

test("API key: create shows the secret once, then it's revocable", async ({ page }) => {
  const orgId = await registerAndCreateOrg(page, Date.now());

  await page.goto(`/dashboard/${orgId}/settings/api-keys`);
  await page.getByPlaceholder("CI pipeline").fill("e2e key");
  await page.getByRole("button", { name: "Create key" }).click();

  // Generous timeout: this shared dev machine's CPU load has been observed
  // swinging between ~50% and ~94% from unrelated processes mid-suite, and a
  // direct curl to the backend confirmed the actual API call itself is fast
  // (<1s) when the machine isn't under that contention — this is a real
  // environment characteristic (confirmed not specific to this endpoint: a
  // later run saw the same class of delay on the register step instead), not
  // an app bug.
  await expect(page.getByText(/edb_/)).toBeVisible({ timeout: 90_000 });

  await page.reload();
  await expect(page.getByText("e2e key")).toBeVisible();
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("e2e key")).not.toBeVisible();
});

test("Webhook: create shows the signing secret once, then it's deletable", async ({ page }) => {
  const orgId = await registerAndCreateOrg(page, Date.now() + 1);

  await page.goto(`/dashboard/${orgId}/settings/webhooks`);
  await page.getByLabel("URL").fill("https://example.com/hooks");
  await page.getByLabel("database.created").check();
  await page.getByRole("button", { name: "Create webhook" }).click();

  await expect(page.getByText(/signing secret/i)).toBeVisible();

  await page.reload();
  await expect(page.getByText("https://example.com/hooks")).toBeVisible();
  await page.getByRole("link", { name: "Deliveries" }).click();
  await expect(page.getByRole("heading", { name: "Deliveries" })).toBeVisible();
});

test("Members: the owner is listed and cannot remove themselves", async ({ page }) => {
  const orgId = await registerAndCreateOrg(page, Date.now() + 2);

  await page.goto(`/dashboard/${orgId}/settings/members`);
  await expect(page.getByText("owner")).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove" })).toHaveCount(0);
});

test("Billing: free plan shows with no invoices yet", async ({ page }) => {
  const orgId = await registerAndCreateOrg(page, Date.now() + 3);

  await page.goto(`/dashboard/${orgId}/billing`);
  await expect(page.getByRole("heading", { name: "Billing" })).toBeVisible();
  await expect(page.getByText("No invoices yet.")).toBeVisible();
});

test("Database detail: shell renders with graceful degradation while not running", async ({
  page,
}) => {
  await registerAndCreateOrg(page, Date.now() + 4);

  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill("F2F6 Project");
  await page.getByLabel("Slug").fill("f2f6-project");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("link", { name: "F2F6 Project" }).click();
  await expect(page).toHaveURL(/\/databases$/);

  await page.getByRole("button", { name: "New database" }).click();
  await page.getByPlaceholder("my-database").fill("f2f6-db");
  await page.getByRole("button", { name: "Create database" }).click();
  await page.getByText("f2f6-db").click();

  await expect(page).toHaveURL(/\/databases\/[^/]+$/);
  await expect(page.getByRole("heading", { name: "f2f6-db" })).toBeVisible();
  // The database never reaches `running` without a real agent — metrics/roles/
  // extensions must degrade gracefully rather than crash the page.
  await expect(page.getByRole("heading", { name: "Metrics" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect" })).toBeDisabled();
  await expect(page.getByText("No roles available yet.")).toBeVisible();
});
