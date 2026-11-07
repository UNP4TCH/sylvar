/** Public (browser-safe) configuration. Pure function so it is testable without Vite. */
export interface PublicEnv {
  apiBaseUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
}

export type EnvResult =
  | { ok: true; env: PublicEnv }
  | { ok: false; missing: string[] };

type RawEnv = Record<string, string | undefined>;

const REQUIRED = ["VITE_API_BASE_URL", "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"] as const;

export function readPublicEnv(raw: RawEnv): EnvResult {
  const missing = REQUIRED.filter((k) => !raw[k] || raw[k]?.startsWith("CHANGE_ME") || raw[k]?.includes("YOUR-PROJECT"));
  if (missing.length > 0) return { ok: false, missing: [...missing] };
  return {
    ok: true,
    env: {
      apiBaseUrl: (raw.VITE_API_BASE_URL as string).replace(/\/+$/, ""),
      supabaseUrl: raw.VITE_SUPABASE_URL as string,
      supabaseAnonKey: raw.VITE_SUPABASE_ANON_KEY as string,
    },
  };
}
