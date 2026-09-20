/**
 * Official TypeScript client for the eminidatabase Control Plane API.
 *
 * Mirrors sdk/eminidatabase_sdk/client.py's PlatformClient exactly: every method
 * is a thin wrapper around one API call — no client-side business logic, no
 * caching, no retries (that all lives in the platform itself). Types come from
 * `types.gen.ts`, generated from the backend's own OpenAPI schema
 * (`npm run generate`, cf. README.md) rather than hand-duplicated, so a backend
 * schema change surfaces here as a type error instead of silent drift.
 */

import { ApiError } from "./exceptions";
import type { components } from "./types.gen";

export type MeResponse = components["schemas"]["MeResponse"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type MfaEnableResponse = components["schemas"]["MfaEnableResponse"];
export type OrganizationResponse = components["schemas"]["OrganizationResponse"];
export type ProjectResponse = components["schemas"]["ProjectResponse"];
export type DatabaseResponse = components["schemas"]["DatabaseResponse"];
export type DatabaseCreateAccepted = components["schemas"]["DatabaseCreateAccepted"];
export type IsolationLevel = components["schemas"]["IsolationLevel"];
export type JobResponse = components["schemas"]["JobResponse"];
export type NotificationResponse = components["schemas"]["NotificationResponse"];
export type RegionResponse = components["schemas"]["RegionResponse"];

const DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1";
const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed"]);

export interface CreateDatabaseOptions {
  isolationLevel?: IsolationLevel;
  cpuLimit?: number;
  ramLimitMb?: number;
  storageLimitGb?: number;
}

export interface WaitForJobOptions {
  intervalMs?: number;
  timeoutMs?: number;
}

export class PlatformClient {
  baseUrl: string;
  token: string | null;

  constructor(baseUrl: string = DEFAULT_BASE_URL, token: string | null = null) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
  }

  private headers(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        ...this.headers(),
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const data = (await resp.json()) as { detail?: string };
        detail = data.detail ?? detail;
      } catch {
        // Body wasn't JSON (or was empty) — fall back to statusText above.
      }
      throw new ApiError(resp.status, detail);
    }
    if (resp.status === 204) {
      return undefined as T;
    }
    const text = await resp.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  // --- Auth -----------------------------------------------------------

  async register(email: string, password: string): Promise<MeResponse> {
    return this.request("POST", "/auth/register", { email, password });
  }

  async login(email: string, password: string, otpCode?: string): Promise<string> {
    const body: Record<string, string> = { email, password };
    if (otpCode) body.otp_code = otpCode;
    const data = await this.request<TokenResponse>("POST", "/auth/login", body);
    this.token = data.access_token;
    return this.token;
  }

  async me(): Promise<MeResponse> {
    return this.request("GET", "/auth/me");
  }

  async enableMfa(): Promise<MfaEnableResponse> {
    return this.request("POST", "/auth/mfa/enable");
  }

  async verifyMfa(otpCode: string): Promise<void> {
    return this.request("POST", "/auth/mfa/verify", { otp_code: otpCode });
  }

  // --- Organizations ----------------------------------------------------

  async createOrganization(name: string, slug: string): Promise<OrganizationResponse> {
    return this.request("POST", "/organizations", { name, slug });
  }

  async listOrganizations(): Promise<OrganizationResponse[]> {
    return this.request("GET", "/organizations");
  }

  async getOrganization(organizationId: string): Promise<OrganizationResponse> {
    return this.request("GET", `/organizations/${organizationId}`);
  }

  // --- Regions ------------------------------------------------------

  async listRegions(): Promise<RegionResponse[]> {
    return this.request("GET", "/regions");
  }

  // --- Projects -----------------------------------------------------------

  async createProject(
    organizationId: string,
    name: string,
    slug: string
  ): Promise<ProjectResponse> {
    return this.request("POST", `/organizations/${organizationId}/projects`, { name, slug });
  }

  async listProjects(organizationId: string): Promise<ProjectResponse[]> {
    return this.request("GET", `/organizations/${organizationId}/projects`);
  }

  async getProject(organizationId: string, projectId: string): Promise<ProjectResponse> {
    return this.request("GET", `/organizations/${organizationId}/projects/${projectId}`);
  }

  // --- Databases ------------------------------------------------------

  private dbPath(organizationId: string, projectId: string, databaseId = ""): string {
    const base = `/organizations/${organizationId}/projects/${projectId}/databases`;
    return databaseId ? `${base}/${databaseId}` : base;
  }

  async createDatabase(
    organizationId: string,
    projectId: string,
    name: string,
    regionCode: string,
    options: CreateDatabaseOptions = {}
  ): Promise<DatabaseCreateAccepted> {
    const payload = {
      name,
      region_code: regionCode,
      isolation_level: options.isolationLevel ?? "shared",
      cpu_limit: options.cpuLimit ?? 1,
      ram_limit_mb: options.ramLimitMb ?? 1024,
      storage_limit_gb: options.storageLimitGb ?? 10,
    };
    return this.request("POST", this.dbPath(organizationId, projectId), payload);
  }

  async listDatabases(organizationId: string, projectId: string): Promise<DatabaseResponse[]> {
    return this.request("GET", this.dbPath(organizationId, projectId));
  }

  async getDatabase(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<DatabaseResponse> {
    return this.request("GET", this.dbPath(organizationId, projectId, databaseId));
  }

  // --- Jobs -------------------------------------------------------------

  async getJob(jobId: string): Promise<JobResponse> {
    return this.request("GET", `/jobs/${jobId}`);
  }

  async waitForJob(jobId: string, options: WaitForJobOptions = {}): Promise<JobResponse> {
    const interval = options.intervalMs ?? 1000;
    const timeout = options.timeoutMs ?? 120_000;
    const start = Date.now();
    for (;;) {
      const job = await this.getJob(jobId);
      if (TERMINAL_JOB_STATUSES.has(job.status)) {
        return job;
      }
      if (Date.now() - start > timeout) {
        throw new Error(`Job ${jobId} did not complete within ${timeout}ms`);
      }
      await new Promise((resolve) => setTimeout(resolve, interval));
    }
  }

  // --- Notifications ----------------------------------------------------

  async listNotifications(): Promise<NotificationResponse[]> {
    return this.request("GET", "/notifications");
  }

  async markNotificationRead(notificationId: string): Promise<void> {
    return this.request("POST", `/notifications/${notificationId}/read`);
  }
}
