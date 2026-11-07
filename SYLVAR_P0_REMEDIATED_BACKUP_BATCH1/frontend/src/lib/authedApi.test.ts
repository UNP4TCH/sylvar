import type { SupabaseClient } from "@supabase/supabase-js";
import { ApiError } from "./api";
import { createAuthedClient, createAuthedGet } from "./authedApi";

function client(opts: { token?: string | null; refreshed?: string | null; refreshError?: boolean }) {
  const auth = {
    getSession: vi.fn().mockResolvedValue({
      data: { session: opts.token ? { access_token: opts.token } : null },
      error: null,
    }),
    refreshSession: vi.fn().mockResolvedValue({
      data: { session: opts.refreshed ? { access_token: opts.refreshed } : null },
      error: opts.refreshError ? { message: "x" } : null,
    }),
  };
  return { c: { auth } as unknown as SupabaseClient, auth };
}

function fetchSeq(...statuses: number[]) {
  const tokens: string[] = [];
  const f = (async (_u: RequestInfo | URL, init?: RequestInit) => {
    tokens.push((init?.headers as Record<string, string>).Authorization);
    const s = statuses.shift() ?? 200;
    return new Response(JSON.stringify(s === 200 ? { ok: true } : { type: "t", title: "U", status: s, detail: "d", instance: "/" }), { status: s });
  }) as typeof fetch;
  return { f, tokens };
}

test("sends the current access token", async () => {
  const { c } = client({ token: "tok1" });
  const { f, tokens } = fetchSeq(200);
  await createAuthedGet(() => c, "http://x", f)("/p");
  expect(tokens).toEqual(["Bearer tok1"]);
});

test("throws 401 without calling the API when signed out", async () => {
  const { c } = client({ token: null });
  const { f, tokens } = fetchSeq(200);
  await expect(createAuthedGet(() => c, "http://x", f)("/p")).rejects.toMatchObject({ status: 401 });
  expect(tokens).toEqual([]);
});

test("refreshes once on 401 and retries with the new token", async () => {
  const { c, auth } = client({ token: "old", refreshed: "new" });
  const { f, tokens } = fetchSeq(401, 200);
  await createAuthedGet(() => c, "http://x", f)("/p");
  expect(tokens).toEqual(["Bearer old", "Bearer new"]);
  expect(auth.refreshSession).toHaveBeenCalledTimes(1);
});

test("a second 401 after refresh is surfaced, no retry loop", async () => {
  const { c } = client({ token: "old", refreshed: "new" });
  const { f, tokens } = fetchSeq(401, 401, 200);
  await expect(createAuthedGet(() => c, "http://x", f)("/p")).rejects.toBeInstanceOf(ApiError);
  expect(tokens.length).toBe(2);
});

test("refresh failure surfaces the original 401", async () => {
  const { c } = client({ token: "old", refreshed: null, refreshError: true });
  const { f } = fetchSeq(401);
  await expect(createAuthedGet(() => c, "http://x", f)("/p")).rejects.toMatchObject({ status: 401 });
});

test("non-401 errors are not retried", async () => {
  const { c, auth } = client({ token: "tok" });
  const { f, tokens } = fetchSeq(503);
  await expect(createAuthedGet(() => c, "http://x", f)("/p")).rejects.toMatchObject({ status: 503 });
  expect(tokens.length).toBe(1);
  expect(auth.refreshSession).not.toHaveBeenCalled();
});

test("concurrent 401s share one refresh (no refresh-token race)", async () => {
  const { c, auth } = client({ token: "old", refreshed: "new" });
  const tokens: string[] = [];
  const f = (async (_u: RequestInfo | URL, init?: RequestInit) => {
    const auth = (init?.headers as Record<string, string>).Authorization;
    tokens.push(auth);
    return auth === "Bearer new"
      ? new Response("{}", { status: 200 })
      : new Response(JSON.stringify({ type: "t", title: "U", status: 401, detail: "d", instance: "/" }), { status: 401 });
  }) as typeof fetch;
  const get = createAuthedGet(() => c, "http://x", f);
  await Promise.all([get("/a"), get("/b"), get("/c")]);
  expect(auth.refreshSession).toHaveBeenCalledTimes(1);
  expect(tokens.filter((t) => t === "Bearer new").length).toBe(3);
});

test("a later 401 triggers a fresh refresh after the first one finished", async () => {
  const { c, auth } = client({ token: "old", refreshed: "new" });
  const f = (async (_u: RequestInfo | URL, init?: RequestInit) =>
    (init?.headers as Record<string, string>).Authorization === "Bearer new"
      ? new Response("{}", { status: 200 })
      : new Response(JSON.stringify({ type: "t", title: "U", status: 401, detail: "d", instance: "/" }), { status: 401 })) as typeof fetch;
  const get = createAuthedGet(() => c, "http://x", f);
  await get("/a");
  await get("/b");
  expect(auth.refreshSession).toHaveBeenCalledTimes(2);
});

test("a throwing refreshSession surfaces the original 401 and does not wedge later refreshes", async () => {
  const { c, auth } = client({ token: "old", refreshed: "new" });
  auth.refreshSession.mockRejectedValueOnce(new Error("boom"));
  const f = (async (_u: RequestInfo | URL, init?: RequestInit) =>
    (init?.headers as Record<string, string>).Authorization === "Bearer new"
      ? new Response("{}", { status: 200 })
      : new Response(JSON.stringify({ type: "t", title: "U", status: 401, detail: "d", instance: "/" }), { status: 401 })) as typeof fetch;
  const get = createAuthedGet(() => c, "http://x", f);
  await expect(get("/a")).rejects.toMatchObject({ status: 401 });
  await expect(get("/b")).resolves.toEqual({});
});

test("authedDelete refreshes once on 401 and retries with new token", async () => {
  const { c, auth } = client({ token: "old", refreshed: "new" });
  const { f, tokens } = fetchSeq(401, 200);
  const clientInstance = createAuthedClient(() => c, "http://x", f);
  await clientInstance.delete("/items/1");
  expect(tokens).toEqual(["Bearer old", "Bearer new"]);
  expect(auth.refreshSession).toHaveBeenCalledTimes(1);
});
