import { useEffect } from "react";
import { useAuthStore } from "../store/authStore";
import ApiStatus from "./ApiStatus";
import AuthForm from "./AuthForm";
import Dashboard from "./Dashboard";

export default function AuthGate({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { status, session, error, notice, init, signIn, signUp, signOut, clearMessages } =
    useAuthStore();

  // init() subscribes synchronously and returns its cleanup, so Strict Mode's
  // mount -> unmount -> mount leaves exactly one live subscription.
  useEffect(() => init(), [init]);

  if (status === "loading") return <p>Loading…</p>;
  if (status === "signed_out")
    return (
      <AuthForm onSignIn={signIn} onSignUp={signUp} error={error} notice={notice}
        onModeChange={clearMessages} />
    );
  return (
    <div className="w-full flex flex-col items-center gap-4">
      <header className="w-full max-w-5xl flex items-center justify-between border-b pb-3 px-4">
        <div className="flex items-center gap-3">
          <span className="font-bold text-lg text-indigo-900 tracking-wide">SYLVAR</span>
          <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
            Pre-Publication CI/CD
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <ApiStatus baseUrl={apiBaseUrl} />
          <span className="text-gray-600">{session?.user.email}</span>
          <button
            className="border rounded px-2.5 py-1 text-gray-700 hover:bg-gray-100 font-medium"
            onClick={() => void signOut()}
          >
            Sign out
          </button>
        </div>
      </header>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <Dashboard apiBaseUrl={apiBaseUrl} />
    </div>
  );
}
