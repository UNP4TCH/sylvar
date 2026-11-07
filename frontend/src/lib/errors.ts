import { ApiError } from "./api";

/**
 * Turns any thrown value into one human-readable line. Surfaces the backend's own problem+json detail,
 * machine code and request id when present so failures can be traced in server logs.
 * Never returns an empty string.
 */
export function formatApiError(err: unknown): string {
  if (err instanceof ApiError) {
    const p = err.problem;
    const parts: string[] = [p?.detail || p?.title || `Request failed`];
    const meta: string[] = [`HTTP ${err.status}`];
    if (p?.code) meta.push(`code ${p.code}`);
    if (p?.request_id) meta.push(`request_id ${p.request_id}`);
    return `${parts[0]} (${meta.join(", ")})`;
  }
  if (err instanceof TypeError) {
    // fetch() rejects with TypeError for network failure, DNS, CORS preflight rejection, mixed content.
    return `Network error: the API could not be reached (${err.message}). Check that the backend is running, VITE_API_BASE_URL is correct and CORS allows this origin.`;
  }
  if (err instanceof Error && err.message) return err.message;
  const s = String(err);
  return s && s !== "[object Object]" ? s : "Unknown error";
}
