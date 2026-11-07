import { StrictMode } from "react";
import { render, screen } from "@testing-library/react";
import AuthGate from "./AuthGate";
import { useAuthStore } from "../store/authStore";

vi.mock("../store/authStore", () => ({ useAuthStore: vi.fn() }));
vi.mock("./ApiStatus", () => ({ default: () => <p>api-status-stub</p> }));

function state(overrides: Record<string, unknown>) {
  const base = {
    status: "loading", session: null, error: null, notice: null,
    init: vi.fn().mockReturnValue(() => undefined),
    signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(), clearMessages: vi.fn(),
  };
  vi.mocked(useAuthStore).mockReturnValue({ ...base, ...overrides } as never);
  return { ...base, ...overrides };
}

test("shows loading while the session resolves and calls init once", () => {
  const s = state({});
  render(<AuthGate apiBaseUrl="http://x" />);
  expect(screen.getByText("Loading…")).toBeInTheDocument();
  expect(s.init).toHaveBeenCalledTimes(1);
});

test("shows the sign-in form when signed out", () => {
  state({ status: "signed_out" });
  render(<AuthGate apiBaseUrl="http://x" />);
  expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("shows the signed-in view with API status and sign-out", () => {
  state({ status: "signed_in", session: { user: { email: "me@x.co" } } });
  render(<AuthGate apiBaseUrl="http://x" />);
  expect(screen.getByText(/me@x.co/)).toBeInTheDocument();
  expect(screen.getByText("api-status-stub")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
});

test("unsubscribes from auth changes on unmount", () => {
  const cleanup = vi.fn();
  state({ status: "signed_out", init: vi.fn().mockReturnValue(cleanup) });
  const { unmount } = render(<AuthGate apiBaseUrl="http://x" />);
  expect(cleanup).not.toHaveBeenCalled();
  unmount();
  expect(cleanup).toHaveBeenCalledTimes(1);
});

test("Strict Mode: init runs twice and the first subscription is cleaned up", () => {
  const cleanup = vi.fn();
  const init = vi.fn().mockReturnValue(cleanup);
  state({ status: "signed_out", init });
  render(
    <StrictMode>
      <AuthGate apiBaseUrl="http://x" />
    </StrictMode>,
  );
  expect(init).toHaveBeenCalledTimes(2);
  expect(cleanup).toHaveBeenCalledTimes(1); // mount -> simulated unmount; second stays live
});
