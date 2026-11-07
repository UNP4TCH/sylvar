import AuthGate from "./components/AuthGate";
import { getEnv } from "./lib/supabase";

function NotConfigured({ missing }: { missing: string[] }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div role="alert" className="max-w-md w-full bg-white rounded-2xl shadow-elevated border border-rose-100 p-8 text-center space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center mx-auto text-xl font-bold">
          !
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-900">Configuration Required</h2>
          <p className="text-sm text-slate-600 mt-1">SYLVAR is not configured.</p>
        </div>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs font-mono text-slate-700 text-left">
          Missing variables in frontend/.env:
          <ul className="list-disc list-inside mt-1 text-rose-600 font-semibold">
            {missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const env = getEnv();
  return (
    <main className="sylvar-app min-h-screen flex flex-col">
      <h1 className="sr-only">SYLVAR</h1>
      {env.ok ? (
        <AuthGate apiBaseUrl={env.env.apiBaseUrl} />
      ) : (
        <NotConfigured missing={env.missing} />
      )}
    </main>
  );
}
