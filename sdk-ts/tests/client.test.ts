import { afterEach, describe, expect, it, vi } from "vitest";

import { PlatformClient } from "../src/client.js";
import type { ApiError } from "../src/exceptions.js";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PlatformClient", () => {
  it("attaches the bearer token once login() has set it", async () => {
    const calls: Array<{ url: string; headers: Record<string, string> }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url: String(url), headers: (init?.headers as Record<string, string>) ?? {} });
        if (String(url).endsWith("/auth/login")) {
          return jsonResponse({ access_token: "tok-123", token_type: "bearer" });
        }
        return jsonResponse({ id: "u1", email: "dev@example.com", mfa_enabled: false });
      })
    );

    const client = new PlatformClient("http://test/api/v1");
    const token = await client.login("dev@example.com", "correct-horse-battery");
    expect(token).toBe("tok-123");
    expect(client.token).toBe("tok-123");

    await client.me();
    const meCall = calls.find((c) => c.url.endsWith("/auth/me"));
    expect(meCall?.headers.Authorization).toBe("Bearer tok-123");
  });

  it("raises ApiError with the backend's status code and detail on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({ detail: "Invalid email or password" }, 401)
      )
    );

    const client = new PlatformClient("http://test/api/v1");
    await expect(client.login("dev@example.com", "wrong")).rejects.toMatchObject({
      statusCode: 401,
      detail: "Invalid email or password",
    } satisfies Partial<ApiError>);
  });

  it("returns undefined for a 204 response instead of parsing an empty body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 }))
    );

    const client = new PlatformClient("http://test/api/v1", "tok");
    await expect(client.verifyMfa("123456")).resolves.toBeUndefined();
  });

  it("waitForJob polls until a terminal status", async () => {
    let call = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        call += 1;
        const status = call < 3 ? "running" : "succeeded";
        return jsonResponse({
          id: "job-1",
          type: "create_database",
          status,
          attempts: call,
          max_attempts: 5,
          error: null,
          result: null,
          resource_type: "database",
          resource_id: "db-1",
          created_at: new Date().toISOString(),
          completed_at: null,
        });
      })
    );

    const client = new PlatformClient("http://test/api/v1", "tok");
    const job = await client.waitForJob("job-1", { intervalMs: 1 });
    expect(job.status).toBe("succeeded");
    expect(call).toBe(3);
  });
});
