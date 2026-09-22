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
export type DatabaseResize = components["schemas"]["DatabaseResize"];
export type IsolationLevel = components["schemas"]["IsolationLevel"];
export type JobResponse = components["schemas"]["JobResponse"];
export type NotificationResponse = components["schemas"]["NotificationResponse"];
export type RegionResponse = components["schemas"]["RegionResponse"];
export type DatabaseConnectionResponse = components["schemas"]["DatabaseConnectionResponse"];
export type DatabaseMetricsResponse = components["schemas"]["DatabaseMetricsResponse"];
export type TableInfo = components["schemas"]["TableInfo"];
export type ExtensionResponse = components["schemas"]["ExtensionResponse"];
export type CredentialScope = components["schemas"]["CredentialScope"];
export type RoleResponse = components["schemas"]["RoleResponse"];
export type RoleCreated = components["schemas"]["RoleCreated"];
export type SqlExecuteResponse = components["schemas"]["SqlExecuteResponse"];
export type QueryExecutionResponse = components["schemas"]["QueryExecutionResponse"];
export type SavedQueryResponse = components["schemas"]["SavedQueryResponse"];
export type BackupResponse = components["schemas"]["BackupResponse"];
export type BackupCreateAccepted = components["schemas"]["BackupCreateAccepted"];
export type RestoreAccepted = components["schemas"]["RestoreAccepted"];
export type BackupPolicyUpdate = components["schemas"]["BackupPolicyUpdate"];
export type PlanResponse = components["schemas"]["PlanResponse"];
export type SubscriptionResponse = components["schemas"]["SubscriptionResponse"];
export type UsageSummaryResponse = components["schemas"]["UsageSummaryResponse"];
export type InvoiceResponse = components["schemas"]["InvoiceResponse"];
export type InvoiceDetailResponse = components["schemas"]["InvoiceDetailResponse"];
export type PaymentResponse = components["schemas"]["PaymentResponse"];
export type WebhookResponse = components["schemas"]["WebhookResponse"];
export type WebhookCreated = components["schemas"]["WebhookCreated"];
export type WebhookDeliveryResponse = components["schemas"]["WebhookDeliveryResponse"];
export type ApiKeyResponse = components["schemas"]["ApiKeyResponse"];
export type ApiKeyCreated = components["schemas"]["ApiKeyCreated"];
export type MembershipResponse = components["schemas"]["MembershipResponse"];
export type MembershipRole = components["schemas"]["MembershipRole"];

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
        const data = (await resp.json()) as { detail?: unknown };
        // FastAPI's own validation errors (422) send `detail` as an array of
        // Pydantic error objects (`{type, loc, msg, input}`), not a string —
        // format them into a readable sentence instead of dumping raw JSON
        // (or crashing a caller that renders `.detail` directly as a React
        // child, which is what an un-coerced object/array would do).
        if (typeof data.detail === "string") {
          detail = data.detail;
        } else if (Array.isArray(data.detail)) {
          detail = data.detail
            .map((issue) => {
              if (issue && typeof issue === "object" && "msg" in issue) {
                const loc = Array.isArray((issue as { loc?: unknown[] }).loc)
                  ? (issue as { loc: unknown[] }).loc.filter((p) => p !== "body").join(".")
                  : undefined;
                const msg = String((issue as { msg: unknown }).msg);
                return loc ? `${loc}: ${msg}` : msg;
              }
              return JSON.stringify(issue);
            })
            .join("; ");
        } else if (data.detail !== undefined) {
          detail = JSON.stringify(data.detail);
        }
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

  async revokeAllSessions(): Promise<void> {
    return this.request("POST", "/auth/sessions/revoke-all");
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

  async deleteProject(organizationId: string, projectId: string): Promise<void> {
    return this.request("DELETE", `/organizations/${organizationId}/projects/${projectId}`);
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

  async deleteDatabase(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<DatabaseCreateAccepted> {
    return this.request(
      "DELETE",
      `${this.dbPath(organizationId, projectId)}/${databaseId}`
    );
  }

  async getDatabase(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<DatabaseResponse> {
    return this.request("GET", this.dbPath(organizationId, projectId, databaseId));
  }

  async suspendDatabase(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<DatabaseCreateAccepted> {
    return this.request("POST", `${this.dbPath(organizationId, projectId, databaseId)}/suspend`);
  }

  async resumeDatabase(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<DatabaseCreateAccepted> {
    return this.request("POST", `${this.dbPath(organizationId, projectId, databaseId)}/resume`);
  }

  async resizeDatabase(
    organizationId: string,
    projectId: string,
    databaseId: string,
    resize: DatabaseResize
  ): Promise<DatabaseResponse> {
    return this.request("POST", `${this.dbPath(organizationId, projectId, databaseId)}/resize`, resize);
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

  // --- Database ops: connection, metrics, tables, extensions -----------

  async getConnection(
    organizationId: string,
    projectId: string,
    databaseId: string,
    credentialId?: string
  ): Promise<DatabaseConnectionResponse> {
    const query = credentialId ? `?credential_id=${encodeURIComponent(credentialId)}` : "";
    return this.request(
      "GET",
      this.dbPath(organizationId, projectId, databaseId) + "/connection" + query
    );
  }

  async getDatabaseMetrics(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<DatabaseMetricsResponse> {
    return this.request("GET", this.dbPath(organizationId, projectId, databaseId) + "/metrics");
  }

  async listTables(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<TableInfo[]> {
    return this.request("GET", this.dbPath(organizationId, projectId, databaseId) + "/tables");
  }

  async listExtensions(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<ExtensionResponse[]> {
    return this.request("GET", this.dbPath(organizationId, projectId, databaseId) + "/extensions");
  }

  async installExtension(
    organizationId: string,
    projectId: string,
    databaseId: string,
    name: string
  ): Promise<{ status: string; name: string }> {
    return this.request(
      "POST",
      this.dbPath(organizationId, projectId, databaseId) + "/extensions",
      { name }
    );
  }

  async dropExtension(
    organizationId: string,
    projectId: string,
    databaseId: string,
    name: string
  ): Promise<void> {
    return this.request(
      "DELETE",
      this.dbPath(organizationId, projectId, databaseId) + `/extensions/${name}`
    );
  }

  // --- Database roles -----------------------------------------------------

  async createRole(
    organizationId: string,
    projectId: string,
    databaseId: string,
    name: string,
    scope: CredentialScope = "app"
  ): Promise<RoleCreated> {
    return this.request(
      "POST",
      this.dbPath(organizationId, projectId, databaseId) + "/roles",
      { name, scope }
    );
  }

  async listRoles(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<RoleResponse[]> {
    return this.request("GET", this.dbPath(organizationId, projectId, databaseId) + "/roles");
  }

  async deleteRole(
    organizationId: string,
    projectId: string,
    databaseId: string,
    credentialId: string
  ): Promise<void> {
    return this.request(
      "DELETE",
      this.dbPath(organizationId, projectId, databaseId) + `/roles/${credentialId}`
    );
  }

  async rotateRole(
    organizationId: string,
    projectId: string,
    databaseId: string,
    credentialId: string
  ): Promise<RoleCreated> {
    return this.request(
      "POST",
      this.dbPath(organizationId, projectId, databaseId) + `/roles/${credentialId}/rotate`
    );
  }

  // --- SQL Editor ------------------------------------------------------

  async executeSql(
    organizationId: string,
    projectId: string,
    databaseId: string,
    query: string,
    roleId?: string
  ): Promise<SqlExecuteResponse> {
    return this.request(
      "POST",
      this.dbPath(organizationId, projectId, databaseId) + "/sql/execute",
      { query, role_id: roleId ?? null }
    );
  }

  async getSqlHistory(
    organizationId: string,
    projectId: string,
    databaseId: string,
    limit = 50
  ): Promise<QueryExecutionResponse[]> {
    return this.request(
      "GET",
      this.dbPath(organizationId, projectId, databaseId) + `/sql/history?limit=${limit}`
    );
  }

  async createSavedQuery(
    organizationId: string,
    projectId: string,
    databaseId: string,
    name: string,
    query: string
  ): Promise<SavedQueryResponse> {
    return this.request(
      "POST",
      this.dbPath(organizationId, projectId, databaseId) + "/sql/saved-queries",
      { name, query }
    );
  }

  async listSavedQueries(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<SavedQueryResponse[]> {
    return this.request(
      "GET",
      this.dbPath(organizationId, projectId, databaseId) + "/sql/saved-queries"
    );
  }

  async deleteSavedQuery(
    organizationId: string,
    projectId: string,
    databaseId: string,
    savedQueryId: string
  ): Promise<void> {
    return this.request(
      "DELETE",
      this.dbPath(organizationId, projectId, databaseId) + `/sql/saved-queries/${savedQueryId}`
    );
  }

  // --- Backups ------------------------------------------------------

  async createBackup(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<BackupCreateAccepted> {
    return this.request("POST", this.dbPath(organizationId, projectId, databaseId) + "/backups");
  }

  async listBackups(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<BackupResponse[]> {
    return this.request("GET", this.dbPath(organizationId, projectId, databaseId) + "/backups");
  }

  async getBackup(
    organizationId: string,
    projectId: string,
    databaseId: string,
    backupId: string
  ): Promise<BackupResponse> {
    return this.request(
      "GET",
      this.dbPath(organizationId, projectId, databaseId) + `/backups/${backupId}`
    );
  }

  async restoreBackup(
    organizationId: string,
    projectId: string,
    databaseId: string,
    backupId: string,
    newName: string
  ): Promise<RestoreAccepted> {
    return this.request(
      "POST",
      this.dbPath(organizationId, projectId, databaseId) + `/backups/${backupId}/restore`,
      { name: newName }
    );
  }

  async getBackupPolicy(
    organizationId: string,
    projectId: string,
    databaseId: string
  ): Promise<BackupPolicyUpdate> {
    return this.request(
      "GET",
      this.dbPath(organizationId, projectId, databaseId) + "/backup-policy"
    );
  }

  async setBackupPolicy(
    organizationId: string,
    projectId: string,
    databaseId: string,
    policy: BackupPolicyUpdate
  ): Promise<BackupPolicyUpdate> {
    return this.request(
      "PUT",
      this.dbPath(organizationId, projectId, databaseId) + "/backup-policy",
      policy
    );
  }

  // --- Billing ------------------------------------------------------

  async listPlans(): Promise<PlanResponse[]> {
    return this.request("GET", "/plans");
  }

  async getSubscription(organizationId: string): Promise<SubscriptionResponse> {
    return this.request("GET", `/organizations/${organizationId}/subscription`);
  }

  async updateSubscription(organizationId: string, planId: string): Promise<SubscriptionResponse> {
    return this.request("PATCH", `/organizations/${organizationId}/subscription`, {
      plan_id: planId,
    });
  }

  async getUsage(organizationId: string): Promise<UsageSummaryResponse> {
    return this.request("GET", `/organizations/${organizationId}/usage`);
  }

  async listInvoices(organizationId: string): Promise<InvoiceResponse[]> {
    return this.request("GET", `/organizations/${organizationId}/invoices`);
  }

  async getInvoice(organizationId: string, invoiceId: string): Promise<InvoiceDetailResponse> {
    return this.request("GET", `/organizations/${organizationId}/invoices/${invoiceId}`);
  }

  async payInvoiceManually(organizationId: string, invoiceId: string): Promise<InvoiceResponse> {
    return this.request("POST", `/organizations/${organizationId}/invoices/${invoiceId}/pay`);
  }

  async payInvoiceWithCrypto(
    organizationId: string,
    invoiceId: string,
    payCurrency?: string
  ): Promise<PaymentResponse> {
    return this.request(
      "POST",
      `/organizations/${organizationId}/invoices/${invoiceId}/pay/crypto`,
      { pay_currency: payCurrency }
    );
  }

  async payInvoiceWithMobileMoney(
    organizationId: string,
    invoiceId: string,
    mode: string,
    phoneNumber: string
  ): Promise<PaymentResponse> {
    return this.request(
      "POST",
      `/organizations/${organizationId}/invoices/${invoiceId}/pay/mobile-money`,
      { mode, phone_number: phoneNumber }
    );
  }

  async listInvoicePayments(organizationId: string, invoiceId: string): Promise<PaymentResponse[]> {
    return this.request(
      "GET",
      `/organizations/${organizationId}/invoices/${invoiceId}/payments`
    );
  }

  // --- Webhooks -----------------------------------------------------

  async createWebhook(
    organizationId: string,
    url: string,
    eventTypes: string[]
  ): Promise<WebhookCreated> {
    return this.request("POST", `/organizations/${organizationId}/webhooks`, {
      url,
      event_types: eventTypes,
    });
  }

  async listWebhooks(organizationId: string): Promise<WebhookResponse[]> {
    return this.request("GET", `/organizations/${organizationId}/webhooks`);
  }

  async deleteWebhook(organizationId: string, webhookId: string): Promise<void> {
    return this.request("DELETE", `/organizations/${organizationId}/webhooks/${webhookId}`);
  }

  async listWebhookDeliveries(
    organizationId: string,
    webhookId: string
  ): Promise<WebhookDeliveryResponse[]> {
    return this.request(
      "GET",
      `/organizations/${organizationId}/webhooks/${webhookId}/deliveries`
    );
  }

  // --- API keys -----------------------------------------------------

  async createApiKey(
    organizationId: string,
    name: string,
    scopes: Record<string, unknown> = {}
  ): Promise<ApiKeyCreated> {
    return this.request("POST", `/organizations/${organizationId}/api-keys`, { name, scopes });
  }

  async listApiKeys(organizationId: string): Promise<ApiKeyResponse[]> {
    return this.request("GET", `/organizations/${organizationId}/api-keys`);
  }

  async revokeApiKey(organizationId: string, apiKeyId: string): Promise<void> {
    return this.request("DELETE", `/organizations/${organizationId}/api-keys/${apiKeyId}`);
  }

  // --- Members ------------------------------------------------------

  async listMembers(organizationId: string): Promise<MembershipResponse[]> {
    return this.request("GET", `/organizations/${organizationId}/members`);
  }

  async addMember(
    organizationId: string,
    email: string,
    role: MembershipRole = "developer"
  ): Promise<MembershipResponse> {
    return this.request("POST", `/organizations/${organizationId}/members`, { email, role });
  }

  async removeMember(organizationId: string, targetUserId: string): Promise<void> {
    return this.request(
      "DELETE",
      `/organizations/${organizationId}/members/${targetUserId}`
    );
  }
}
