import { useEffect } from "react";
import { useAuthStore } from "../store/authStore";
import AuthForm from "./AuthForm";
import Dashboard from "./Dashboard";

export default function AuthGate({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { status, session, error, notice, init, signIn, signUp, signOut, clearMessages } =
    useAuthStore();

  useEffect(() => init(), [init]);

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-[#0b0b0d] flex items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-[#9e938c] font-medium">
          <svg className="animate-spin h-5 w-5 text-[#ff6845]" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Loading…
        </div>
      </div>
    );
  }

  if (status === "signed_out") {
    return (
      <AuthForm
        onSignIn={signIn}
        onSignUp={signUp}
        error={error}
        notice={notice}
        onModeChange={clearMessages}
      />
    );
  }

  return (
    <div className="min-h-screen w-full bg-[#0b0b0d] text-[#e8e6e3] flex flex-col m-0 p-0 overflow-x-hidden">
      {error && (
        <div className="w-full px-6 pt-3 bg-[#0b0b0d]">
          <div role="alert" className="p-3 bg-[#2a1917] border border-[#743b31] text-[#ff9a85] rounded-xl text-xs flex items-center justify-between">
            <span>{error}</span>
          </div>
        </div>
      )}
      <Dashboard
        apiBaseUrl={apiBaseUrl}
        sessionUserEmail={session?.user.email}
        onSignOut={() => void signOut()}
      />
    </div>
  );
}
