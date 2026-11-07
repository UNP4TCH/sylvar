import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { create } from "zustand";
import { getSupabase } from "../lib/supabase";

export type AuthStatus = "loading" | "signed_out" | "signed_in";

export interface AuthState {
  status: AuthStatus;
  session: Session | null;
  error: string | null;
  notice: string | null;
  /** Subscribes synchronously and returns the cleanup. Safe to call twice (React Strict Mode). */
  init: () => () => void;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  clearMessages: () => void;
}

const GENERIC_FAILURE = "Something went wrong. Please try again.";

function messageOf(err: unknown): string {
  return err instanceof Error && err.message ? err.message : GENERIC_FAILURE;
}

/** Factory takes the client getter so tests can inject a mock; the app uses getSupabase. */
export function createAuthStore(getClient: () => SupabaseClient = getSupabase) {
  return create<AuthState>((set) => ({
    status: "loading",
    session: null,
    error: null,
    notice: null,

    init: () => {
      let disposed = false;
      let eventSeen = false; // an auth event is newer than any getSession() result
      let unsubscribe: () => void = () => undefined;
      try {
        const supabase = getClient();
        // Subscribe FIRST so no event can slip between getSession() and subscribing.
        // Callback only sets state: calling Supabase APIs inside it can deadlock.
        const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
          if (disposed) return;
          eventSeen = true;
          set({ status: session ? "signed_in" : "signed_out", session });
        });
        unsubscribe = () => sub.subscription.unsubscribe();
        supabase.auth
          .getSession()
          .then(({ data, error }) => {
            if (disposed || eventSeen) return; // stale: a newer event or a disposed instance
            if (error) set({ status: "signed_out", session: null, error: error.message });
            else set({ status: data.session ? "signed_in" : "signed_out", session: data.session });
          })
          .catch((err: unknown) => {
            if (disposed || eventSeen) return;
            set({ status: "signed_out", session: null, error: messageOf(err) });
          });
      } catch (err) {
        set({ status: "signed_out", session: null, error: messageOf(err) });
      }
      return () => {
        disposed = true;
        unsubscribe();
      };
    },

    signIn: async (email, password) => {
      set({ error: null, notice: null });
      try {
        const { error } = await getClient().auth.signInWithPassword({ email, password });
        if (error) set({ error: error.message });
      } catch (err) {
        set({ error: messageOf(err) });
      }
    },

    signUp: async (email, password) => {
      set({ error: null, notice: null });
      try {
        const { data, error } = await getClient().auth.signUp({ email, password });
        if (error) set({ error: error.message });
        else if (!data.session)
          // Whether confirmation is required depends on the project's Supabase settings (UNVERIFIED).
          set({ notice: "Account created. If email confirmation is enabled, check your inbox before signing in." });
      } catch (err) {
        set({ error: messageOf(err) });
      }
    },

    signOut: async () => {
      try {
        const { error } = await getClient().auth.signOut();
        if (error) set({ error: error.message });
      } catch (err) {
        set({ error: messageOf(err) });
      }
    },

    clearMessages: () => set({ error: null, notice: null }),
  }));
}

export const useAuthStore = createAuthStore();
