import { render, screen } from "@testing-library/react";
import App from "./App";
import { getEnv } from "./lib/supabase";

// Isolate from any real local frontend/.env so tests are deterministic.
vi.mock("./lib/supabase", () => ({ getEnv: vi.fn(), getSupabase: vi.fn() }));

test("renders the product name", () => {
  vi.mocked(getEnv).mockReturnValue({ ok: false, missing: ["VITE_API_BASE_URL"] });
  render(<App />);
  expect(screen.getByRole("heading", { name: "SYLVAR" })).toBeInTheDocument();
});

test("shows a configuration notice when public env is missing", () => {
  vi.mocked(getEnv).mockReturnValue({ ok: false, missing: ["VITE_SUPABASE_URL"] });
  render(<App />);
  expect(screen.getByRole("alert")).toHaveTextContent("not configured");
  expect(screen.getByRole("alert")).toHaveTextContent("VITE_SUPABASE_URL");
});
