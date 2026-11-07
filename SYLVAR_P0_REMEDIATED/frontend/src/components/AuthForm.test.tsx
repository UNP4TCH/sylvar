import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AuthForm from "./AuthForm";

function setup(extra: Partial<Parameters<typeof AuthForm>[0]> = {}) {
  const onSignIn = vi.fn().mockResolvedValue(undefined);
  const onSignUp = vi.fn().mockResolvedValue(undefined);
  render(<AuthForm onSignIn={onSignIn} onSignUp={onSignUp} error={null} {...extra} />);
  return { onSignIn, onSignUp };
}

function fill(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

test("submits sign-in with trimmed email", async () => {
  const { onSignIn, onSignUp } = setup();
  fill("  a@b.co ", "pw-123456");
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() => expect(onSignIn).toHaveBeenCalledWith("a@b.co", "pw-123456"));
  expect(onSignUp).not.toHaveBeenCalled();
});

test("toggles to sign-up and submits sign-up", async () => {
  const onModeChange = vi.fn();
  const { onSignUp } = setup({ onModeChange });
  fireEvent.click(screen.getByRole("button", { name: /need an account/i }));
  expect(onModeChange).toHaveBeenCalled();
  expect(screen.getByRole("heading", { name: "Create account" })).toBeInTheDocument();
  fill("n@b.co", "pw-123456");
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  await waitFor(() => expect(onSignUp).toHaveBeenCalledWith("n@b.co", "pw-123456"));
});

test("renders error and notice messages", () => {
  setup({ error: "Invalid login credentials", notice: "Check your inbox" });
  expect(screen.getByRole("alert")).toHaveTextContent("Invalid login credentials");
  expect(screen.getByRole("status")).toHaveTextContent("Check your inbox");
});

test("password field is masked and has no client-side length policy", () => {
  setup();
  const pw = screen.getByLabelText("Password") as HTMLInputElement;
  expect(pw.type).toBe("password");
  expect(pw.minLength).toBe(-1);
});
