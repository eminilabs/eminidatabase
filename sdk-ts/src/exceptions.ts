/** Mirrors sdk/eminidatabase_sdk/exceptions.py's ApiError exactly — the API's own
 * error shape (`{"detail": ...}`) surfaced as a typed exception rather than
 * forcing callers to inspect status codes themselves. */
export class ApiError extends Error {
  readonly statusCode: number;
  readonly detail: string;

  constructor(statusCode: number, detail: string) {
    super(`API error ${statusCode}: ${detail}`);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.detail = detail;
  }
}
