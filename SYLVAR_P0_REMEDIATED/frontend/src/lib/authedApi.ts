import type { SupabaseClient } from "@supabase/supabase-js";
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from "./api";

/**
 * Authenticated API calls against the backend. The token is read fresh from the Supabase client on every
 * call (it auto-refreshes). On a 401 we refresh the session once and retry; a second 401 is surfaced.
 * The frontend never decides authorization — the backend verifies the JWT (ADR-009).
 */
export function createAuthedClient(
  getClient: () => SupabaseClient,
  baseUrl: string,
  fetchImpl?: typeof fetch,
) {
  let refreshInFlight: Promise<string | null> | null = null;
  function refreshToken(): Promise<string | null> {
    if (!refreshInFlight) {
      const p = (async () => {
        const { data, error } = await getClient().auth.refreshSession();
        return error ? null : (data.session?.access_token ?? null);
      })();
      refreshInFlight = p;
      const clear = () => {
        if (refreshInFlight === p) refreshInFlight = null;
      };
      void p.then(clear, clear);
    }
    return refreshInFlight;
  }

  async function currentToken(): Promise<string | null> {
    const { data } = await getClient().auth.getSession();
    return data.session?.access_token ?? null;
  }

  async function authedGet<T>(path: string, signal?: AbortSignal): Promise<T> {
    const token = await currentToken();
    if (!token) throw new ApiError(401, null);
    try {
      return await apiGet<T>(path, { baseUrl, accessToken: token, signal, fetchImpl });
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 401) throw err;
      let refreshed: string | null = null;
      try {
        refreshed = await refreshToken();
      } catch {
        refreshed = null;
      }
      if (!refreshed) throw err;
      return apiGet<T>(path, { baseUrl, accessToken: refreshed, signal, fetchImpl });
    }
  }

  async function authedPost<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    const token = await currentToken();
    if (!token) throw new ApiError(401, null);
    try {
      return await apiPost<T>(path, body, { baseUrl, accessToken: token, signal, fetchImpl });
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 401) throw err;
      let refreshed: string | null = null;
      try {
        refreshed = await refreshToken();
      } catch {
        refreshed = null;
      }
      if (!refreshed) throw err;
      return apiPost<T>(path, body, { baseUrl, accessToken: refreshed, signal, fetchImpl });
    }
  }

  async function authedPatch<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    const token = await currentToken();
    if (!token) throw new ApiError(401, null);
    try {
      return await apiPatch<T>(path, body, { baseUrl, accessToken: token, signal, fetchImpl });
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 401) throw err;
      let refreshed: string | null = null;
      try {
        refreshed = await refreshToken();
      } catch {
        refreshed = null;
      }
      if (!refreshed) throw err;
      return apiPatch<T>(path, body, { baseUrl, accessToken: refreshed, signal, fetchImpl });
    }
  }

  async function authedDelete<T>(path: string, signal?: AbortSignal): Promise<T> {
    const token = await currentToken();
    if (!token) throw new ApiError(401, null);
    try {
      return await apiDelete<T>(path, { baseUrl, accessToken: token, signal, fetchImpl });
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 401) throw err;
      let refreshed: string | null = null;
      try {
        refreshed = await refreshToken();
      } catch {
        refreshed = null;
      }
      if (!refreshed) throw err;
      return apiDelete<T>(path, { baseUrl, accessToken: refreshed, signal, fetchImpl });
    }
  }

  return { get: authedGet, post: authedPost, patch: authedPatch, delete: authedDelete };
}

export function createAuthedGet(
  getClient: () => SupabaseClient,
  baseUrl: string,
  fetchImpl?: typeof fetch,
) {
  return createAuthedClient(getClient, baseUrl, fetchImpl).get;
}
