/**
 * Single source of truth for API base URL and request path composition.
 * Avoids double-prefixing /api when base already ends with /api.
 */

/** Base URL for API requests. Empty string = same origin. Set VITE_API_BASE_URL in .env to override. */
export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

/**
 * Build full API URL for a path.
 * - If API_BASE_URL ends with "/api", path is appended directly (no extra /api).
 * - Otherwise path is prefixed with "/api/" (or base + "/api/" when base is set).
 * @param path - Path without leading slash, e.g. "races/2025_1/replay/track"
 */
export function buildApiUrl(path: string): string {
  const base = API_BASE_URL.replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path.slice(1) : path;
  if (base.endsWith("/api")) {
    return normalizedPath ? `${base}/${normalizedPath}` : base;
  }
  const apiPath = `api/${normalizedPath}`;
  return base ? `${base}/${apiPath}` : `/${apiPath}`;
}
