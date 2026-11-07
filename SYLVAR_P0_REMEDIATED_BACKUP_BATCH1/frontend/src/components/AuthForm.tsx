import { useState, type FormEvent } from "react";

interface Props {
  onSignIn: (email: string, password: string) => Promise<void>;
  onSignUp: (email: string, password: string) => Promise<void>;
  error: string | null;
  notice?: string | null;
  onModeChange?: () => void;
}

export default function AuthForm({ onSignIn, onSignUp, error, notice, onModeChange }: Props) {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await (mode === "signin" ? onSignIn : onSignUp)(email.trim(), password);
    } finally {
      setBusy(false);
    }
  }

  function toggle() {
    setMode(mode === "signin" ? "signup" : "signin");
    onModeChange?.();
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3 w-80">
      <h2 className="text-xl font-semibold">{mode === "signin" ? "Sign in" : "Create account"}</h2>
      <label className="flex flex-col text-sm">
        Email
        <input type="email" required autoComplete="email" value={email}
          onChange={(e) => setEmail(e.target.value)} className="border rounded px-2 py-1" />
      </label>
      <label className="flex flex-col text-sm">
        Password
        <input type="password" required
          autoComplete={mode === "signin" ? "current-password" : "new-password"}
          value={password} onChange={(e) => setPassword(e.target.value)}
          className="border rounded px-2 py-1" />
      </label>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {notice && <p role="status" className="text-sm text-green-700">{notice}</p>}
      <button type="submit" disabled={busy} className="border rounded px-3 py-1">
        {mode === "signin" ? "Sign in" : "Sign up"}
      </button>
      <button type="button" className="text-sm underline" onClick={toggle}>
        {mode === "signin" ? "Need an account? Sign up" : "Have an account? Sign in"}
      </button>
    </form>
  );
}
