import { expect, test } from "@playwright/test";

test("an expired session during a client-side navigation redirects to login instead of crashing", async ({
  page,
  context,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  const unique = Date.now();
  const email = `expirycheck-${unique}@example.com`;

  await page.goto("http://127.0.0.1:3000/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/organizations\/new/, { timeout: 60_000 });

  await page.getByLabel("Name").fill("Expiry Org");
  await page.getByLabel("Slug").fill(`expiry-org-${unique}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/projects$/);

  // Simulate the token aging out mid-session without a full page reload —
  // exactly what happens after 30 days of real use (ACCESS_TOKEN_EXPIRE_MINUTES).
  const expiredJwt =
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmYWtlIiwiZXhwIjoxNzAwMDAwMDAwfQ.invalidsignature";
  await context.addCookies([
    {
      name: "eminidb_session",
      value: expiredJwt,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
    },
  ]);

  // A client-side (soft) navigation via an in-app <Link> — this is the path
  // the top-level dashboard layout's own me() check does NOT re-run for.
  await page.getByRole("link", { name: "Billing" }).click();

  await expect(page).toHaveURL(/\/login$/, { timeout: 15_000 });
  expect(pageErrors).toEqual([]);
});
