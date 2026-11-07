/** Minimal typed API client. Sends the Supabase access token as a Bearer token. */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code?: string;
  request_id?: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly problem: ProblemDetails | null,
  ) {
    super(problem?.detail ?? `Request failed with status ${status}`);
    this.name = "ApiError";
  }
}

export interface ApiOptions {
  baseUrl: string;
  accessToken?: string | null;
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
}

export async function apiGet<T>(path: string, opts: ApiOptions): Promise<T> {
  const doFetch = opts.fetchImpl ?? fetch;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.accessToken) headers.Authorization = `Bearer ${opts.accessToken}`;
  const response = await doFetch(`${opts.baseUrl}${path}`, { headers, signal: opts.signal });
  if (!response.ok) {
    let problem: ProblemDetails | null = null;
    try {
      problem = (await response.json()) as ProblemDetails;
    } catch {
      problem = null; // non-JSON error body; ApiError still carries the status
    }
    throw new ApiError(response.status, problem);
  }
  return (await response.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown, opts: ApiOptions): Promise<T> {
  const doFetch = opts.fetchImpl ?? fetch;
  const headers: Record<string, string> = { Accept: "application/json" };
  let reqBody: BodyInit | undefined;
  if (body instanceof FormData) {
    reqBody = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    reqBody = JSON.stringify(body);
  }
  if (opts.accessToken) headers.Authorization = `Bearer ${opts.accessToken}`;
  const response = await doFetch(`${opts.baseUrl}${path}`, {
    method: "POST",
    headers,
    body: reqBody,
    signal: opts.signal,
  });
  if (!response.ok) {
    let problem: ProblemDetails | null = null;
    try {
      problem = (await response.json()) as ProblemDetails;
    } catch {
      problem = null;
    }
    throw new ApiError(response.status, problem);
  }
  return (await response.json()) as T;
}

export async function apiPatch<T>(path: string, body: unknown, opts: ApiOptions): Promise<T> {
  const doFetch = opts.fetchImpl ?? fetch;
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (opts.accessToken) headers.Authorization = `Bearer ${opts.accessToken}`;
  const response = await doFetch(`${opts.baseUrl}${path}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  if (!response.ok) {
    let problem: ProblemDetails | null = null;
    try {
      problem = (await response.json()) as ProblemDetails;
    } catch {
      problem = null;
    }
    throw new ApiError(response.status, problem);
  }
  return (await response.json()) as T;
}

export async function apiDelete<T>(path: string, opts: ApiOptions): Promise<T> {
  const doFetch = opts.fetchImpl ?? fetch;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.accessToken) headers.Authorization = `Bearer ${opts.accessToken}`;
  const response = await doFetch(`${opts.baseUrl}${path}`, {
    method: "DELETE",
    headers,
    signal: opts.signal,
  });
  if (!response.ok) {
    let problem: ProblemDetails | null = null;
    try {
      problem = (await response.json()) as ProblemDetails;
    } catch {
      problem = null;
    }
    throw new ApiError(response.status, problem);
  }
  return (await response.json()) as T;
}
