import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { readPublicEnv, type EnvResult } from "./env";

let client: SupabaseClient | null = null;

export function getEnv(): EnvResult {
  return readPublicEnv(import.meta.env as Record<string, string | undefined>);
}

/** Lazily creates the browser client. Throws if public config is missing/placeholder. */
export function getSupabase(): SupabaseClient {
  if (client) return client;
  const result = getEnv();
  if (!result.ok) throw new Error(`Missing configuration: ${result.missing.join(", ")}`);
  client = createClient(result.env.supabaseUrl, result.env.supabaseAnonKey);
  return client;
}
