import { useEffect, useState } from "react";
import { apiGet } from "../lib/api";

type State = "checking" | "alive" | "unreachable";

/** Public liveness probe only (GET /health). Not an authorization signal. */
export default function ApiStatus({ baseUrl, fetchImpl }: { baseUrl: string; fetchImpl?: typeof fetch }) {
  const [state, setState] = useState<State>("checking");
  useEffect(() => {
    const ctrl = new AbortController();
    apiGet<{ status: string }>("/health", { baseUrl, signal: ctrl.signal, fetchImpl })
      .then((r) => setState(r.status === "alive" ? "alive" : "unreachable"))
      .catch(() => {
        if (!ctrl.signal.aborted) setState("unreachable");
      });
    return () => ctrl.abort();
  }, [baseUrl, fetchImpl]);
  return <p className="text-sm" data-testid="api-status">API: {state}</p>;
}
