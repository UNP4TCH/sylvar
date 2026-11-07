import AuthGate from "./components/AuthGate";
import { getEnv } from "./lib/supabase";

function NotConfigured({ missing }: { missing: string[] }) {
  return (
    <div role="alert" className="max-w-md text-center">
      <p className="font-semibold">SYLVAR is not configured.</p>
      <p className="text-sm">Set in frontend/.env: {missing.join(", ")}</p>
    </div>
  );
}

export default function App() {
  const env = getEnv();
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6">
      <h1 className="text-2xl font-semibold">SYLVAR</h1>
      {env.ok ? <AuthGate apiBaseUrl={env.env.apiBaseUrl} /> : <NotConfigured missing={env.missing} />}
    </main>
  );
}
