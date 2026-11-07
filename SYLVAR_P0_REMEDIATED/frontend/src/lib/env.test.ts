import { readPublicEnv } from "./env";

const good = {
  VITE_API_BASE_URL: "http://localhost:8000/api/v1/",
  VITE_SUPABASE_URL: "https://abc.supabase.co",
  VITE_SUPABASE_ANON_KEY: "anon-key",
};

test("accepts complete config and trims trailing slash", () => {
  const r = readPublicEnv(good);
  expect(r.ok).toBe(true);
  if (r.ok) expect(r.env.apiBaseUrl).toBe("http://localhost:8000/api/v1");
});

test("reports missing and placeholder values", () => {
  const r = readPublicEnv({ ...good, VITE_SUPABASE_ANON_KEY: "CHANGE_ME", VITE_SUPABASE_URL: undefined });
  expect(r).toEqual({ ok: false, missing: ["VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"] });
});

test("rejects the example project URL placeholder", () => {
  const r = readPublicEnv({ ...good, VITE_SUPABASE_URL: "https://YOUR-PROJECT.supabase.co" });
  expect(r.ok).toBe(false);
});
