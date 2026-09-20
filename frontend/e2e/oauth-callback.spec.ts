import { expect, test } from "@playwright/test";

const BACKEND_URL = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000/api/v1";

/**
 * Simulates what backend/app/api/v1/endpoints/auth.py's oauth_callback
 * redirects to on success — a real Google/GitHub consent screen can't be
 * automated here (same documented limitation as FedaPay's manual mobile
 * money approval step), but the frontend's half of the hand-off (reading the
 * URL fragment, exchanging it for a cookie, landing on /dashboard) is fully
 * exercisable with a real token obtained directly from the backend.
 */
test("a token in the callback URL fragment becomes a working session", async ({ page, request }) => {
  const unique = Date.now();
  const email = `e2e-oauth-${unique}@example.com`;
  const password = "correct-horse-battery-staple";

  await request.post(`${BACKEND_URL}/auth/register`, { data: { email, password } });
  const loginResp = await request.post(`${BACKEND_URL}/auth/login`, { data: { email, password } });
  const { access_token: token } = await loginResp.json();
  expect(token).toBeTruthy();

  await page.goto(`/auth/callback#access_token=${token}`);
  await expect(page).toHaveURL(/\/dashboard/);

  // The cookie genuinely works for subsequent navigation, not just the one redirect.
  await page.goto("/dashboard/settings/security");
  await expect(page.getByRole("heading", { name: "Security" })).toBeVisible();
});

test("an ?error= from the backend is shown, not silently swallowed", async ({ page }) => {
  await page.goto("/auth/callback?error=MFA%20is%20enabled%20on%20this%20account");
  // Next's own route announcer is also role="alert" (empty), so scope past it.
  await expect(page.getByText("MFA is enabled on this account")).toBeVisible();
});
