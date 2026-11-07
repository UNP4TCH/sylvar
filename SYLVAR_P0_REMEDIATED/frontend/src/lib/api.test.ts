import { ApiError, apiDelete, apiGet } from "./api";

function mockFetch(status: number, body: unknown): typeof fetch {
  return (async () =>
    new Response(typeof body === "string" ? body : JSON.stringify(body), { status })) as typeof fetch;
}

test("sends bearer token and returns JSON", async () => {
  let seen: RequestInit | undefined;
  const f = (async (_u: RequestInfo | URL, init?: RequestInit) => {
    seen = init;
    return new Response(JSON.stringify({ status: "alive" }), { status: 200 });
  }) as typeof fetch;
  const out = await apiGet<{ status: string }>("/health", { baseUrl: "http://x/api/v1", accessToken: "tok", fetchImpl: f });
  expect(out.status).toBe("alive");
  expect((seen?.headers as Record<string, string>).Authorization).toBe("Bearer tok");
});

test("omits Authorization when no token", async () => {
  let seen: RequestInit | undefined;
  const f = (async (_u: RequestInfo | URL, init?: RequestInit) => {
    seen = init;
    return new Response("{}", { status: 200 });
  }) as typeof fetch;
  await apiGet("/health", { baseUrl: "http://x", fetchImpl: f });
  expect((seen?.headers as Record<string, string>).Authorization).toBeUndefined();
});

test("maps problem+json errors to ApiError", async () => {
  const problem = { type: "t", title: "Unauthorized", status: 401, detail: "Token has expired.", instance: "/x", code: "TOKEN_EXPIRED" };
  await expect(apiGet("/x", { baseUrl: "http://x", fetchImpl: mockFetch(401, problem) })).rejects.toMatchObject({
    status: 401,
    problem: { code: "TOKEN_EXPIRED" },
  });
});

test("handles non-JSON error bodies", async () => {
  const err = await apiGet("/x", { baseUrl: "http://x", fetchImpl: mockFetch(502, "<html>bad gateway</html>") }).catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect((err as ApiError).problem).toBeNull();
});

test("apiDelete sends DELETE method with bearer token", async () => {
  let seenMethod: string | undefined;
  let seenAuth: string | undefined;
  const f = (async (_u: RequestInfo | URL, init?: RequestInit) => {
    seenMethod = init?.method;
    seenAuth = (init?.headers as Record<string, string>).Authorization;
    return new Response(JSON.stringify({ deleted: true }), { status: 200 });
  }) as typeof fetch;
  const out = await apiDelete<{ deleted: boolean }>("/items/1", { baseUrl: "http://x/api/v1", accessToken: "tok", fetchImpl: f });
  expect(out.deleted).toBe(true);
  expect(seenMethod).toBe("DELETE");
  expect(seenAuth).toBe("Bearer tok");
});
