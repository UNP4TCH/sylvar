import type { SupabaseClient } from "@supabase/supabase-js";
import { createAuthStore } from "./authStore";

type Session = { access_token: string; user: { email: string } };
const SESSION: Session = { access_token: "t", user: { email: "a@b.c" } };

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

function fakeClient(overrides: Record<string, unknown> = {}) {
  const listeners: Array<(e: string, s: unknown) => void> = [];
  const unsubscribes: Array<ReturnType<typeof vi.fn>> = [];
  const auth = {
    getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
    onAuthStateChange: vi.fn((cb: (e: string, s: unknown) => void) => {
      listeners.push(cb);
      const unsubscribe = vi.fn();
      unsubscribes.push(unsubscribe);
      return { data: { subscription: { unsubscribe } } };
    }),
    signInWithPassword: vi.fn().mockResolvedValue({ error: null }),
    signUp: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
    signOut: vi.fn().mockResolvedValue({ error: null }),
    ...overrides,
  };
  return {
    client: { auth } as unknown as SupabaseClient,
    auth,
    emit: (s: unknown, i = listeners.length - 1) => listeners[i]?.("SIGNED_IN", s),
    unsubscribes,
  };
}

test("init subscribes synchronously and resolves signed_out when there is no session", async () => {
  const f = fakeClient();
  const store = createAuthStore(() => f.client);
  const cleanup = store.getState().init();
  expect(f.auth.onAuthStateChange).toHaveBeenCalledTimes(1); // before any await
  expect(typeof cleanup).toBe("function");
  await vi.waitFor(() => expect(store.getState().status).toBe("signed_out"));
});

test("init resolves signed_in from an existing session", async () => {
  const f = fakeClient({ getSession: vi.fn().mockResolvedValue({ data: { session: SESSION }, error: null }) });
  const store = createAuthStore(() => f.client);
  store.getState().init();
  await vi.waitFor(() => expect(store.getState().status).toBe("signed_in"));
});

test("a newer auth event is not overwritten by a late getSession result", async () => {
  const d = deferred<{ data: { session: null }; error: null }>();
  const f = fakeClient({ getSession: vi.fn().mockReturnValue(d.promise) });
  const store = createAuthStore(() => f.client);
  store.getState().init();
  f.emit(SESSION);
  expect(store.getState().status).toBe("signed_in");
  d.resolve({ data: { session: null }, error: null }); // stale "no session"
  await d.promise;
  await Promise.resolve();
  expect(store.getState().status).toBe("signed_in");
});

test("cleanup unsubscribes and later events / getSession results are ignored", async () => {
  const d = deferred<{ data: { session: Session }; error: null }>();
  const f = fakeClient({ getSession: vi.fn().mockReturnValue(d.promise) });
  const store = createAuthStore(() => f.client);
  const cleanup = store.getState().init();
  cleanup();
  expect(f.unsubscribes[0]).toHaveBeenCalledTimes(1);
  f.emit(SESSION);
  d.resolve({ data: { session: SESSION }, error: null });
  await d.promise;
  await Promise.resolve();
  expect(store.getState().status).toBe("loading");
});

test("Strict Mode double init: disposed first instance cannot overwrite the second", async () => {
  const first = deferred<{ data: { session: null }; error: null }>();
  const getSession = vi
    .fn()
    .mockReturnValueOnce(first.promise)
    .mockResolvedValueOnce({ data: { session: SESSION }, error: null });
  const f = fakeClient({ getSession });
  const store = createAuthStore(() => f.client);
  const cleanup1 = store.getState().init(); // mount
  cleanup1(); // simulated Strict Mode unmount
  store.getState().init(); // remount
  await vi.waitFor(() => expect(store.getState().status).toBe("signed_in"));
  first.resolve({ data: { session: null }, error: null }); // late stale result from instance 1
  await first.promise;
  await Promise.resolve();
  expect(store.getState().status).toBe("signed_in");
  expect(f.unsubscribes[0]).toHaveBeenCalledTimes(1);
  expect(f.unsubscribes[1]).not.toHaveBeenCalled();
});

test("getSession error leaves user signed out with message", async () => {
  const f = fakeClient({ getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: { message: "boom" } }) });
  const store = createAuthStore(() => f.client);
  store.getState().init();
  await vi.waitFor(() => expect(store.getState().error).toBe("boom"));
  expect(store.getState().status).toBe("signed_out");
});

test("getSession rejection is handled, not an unhandled rejection", async () => {
  const f = fakeClient({ getSession: vi.fn().mockRejectedValue(new Error("network down")) });
  const store = createAuthStore(() => f.client);
  store.getState().init();
  await vi.waitFor(() => expect(store.getState().error).toBe("network down"));
  expect(store.getState().status).toBe("signed_out");
});

test("init with a failing client getter leaves user signed out with an error", () => {
  const store = createAuthStore(() => {
    throw new Error("Missing configuration: VITE_SUPABASE_URL");
  });
  const cleanup = store.getState().init();
  expect(store.getState().status).toBe("signed_out");
  expect(store.getState().error).toMatch(/Missing configuration/);
  expect(() => cleanup()).not.toThrow();
});

test("signIn surfaces provider errors", async () => {
  const f = fakeClient({ signInWithPassword: vi.fn().mockResolvedValue({ error: { message: "Invalid login credentials" } }) });
  const store = createAuthStore(() => f.client);
  await store.getState().signIn("a@b.c", "wrong-password");
  expect(store.getState().error).toBe("Invalid login credentials");
});

test("signUp without a session sets a conditional confirmation notice", async () => {
  const f = fakeClient();
  const store = createAuthStore(() => f.client);
  await store.getState().signUp("a@b.c", "password123");
  expect(store.getState().notice).toMatch(/if email confirmation is enabled/i);
  expect(store.getState().error).toBeNull();
});

test("signUp with an immediate session sets no notice", async () => {
  const f = fakeClient({ signUp: vi.fn().mockResolvedValue({ data: { session: SESSION }, error: null }) });
  const store = createAuthStore(() => f.client);
  await store.getState().signUp("a@b.c", "password123");
  expect(store.getState().notice).toBeNull();
});

test("thrown client errors become error messages, not crashes", async () => {
  const f = fakeClient({ signInWithPassword: vi.fn().mockRejectedValue(new Error("network down")) });
  const store = createAuthStore(() => f.client);
  await store.getState().signIn("a@b.c", "pw");
  expect(store.getState().error).toBe("network down");
});

test("clearMessages resets error and notice", async () => {
  const f = fakeClient({ signInWithPassword: vi.fn().mockResolvedValue({ error: { message: "bad" } }) });
  const store = createAuthStore(() => f.client);
  await store.getState().signIn("a@b.c", "pw");
  store.getState().clearMessages();
  expect(store.getState().error).toBeNull();
  expect(store.getState().notice).toBeNull();
});

test("signOut surfaces provider errors", async () => {
  const f = fakeClient({ signOut: vi.fn().mockResolvedValue({ error: { message: "nope" } }) });
  const store = createAuthStore(() => f.client);
  await store.getState().signOut();
  expect(store.getState().error).toBe("nope");
});
