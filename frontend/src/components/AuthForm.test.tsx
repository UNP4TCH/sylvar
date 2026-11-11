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

test("toggles password visibility when show/hide button is clicked", () => {
  setup();
  const pw = screen.getByLabelText("Password") as HTMLInputElement;
  expect(pw.type).toBe("password");

  const toggleBtn = screen.getByRole("button", { name: "Show password" });
  fireEvent.click(toggleBtn);
  expect(pw.type).toBe("text");
  expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
  expect(pw.type).toBe("password");
  expect(screen.getByRole("button", { name: "Show password" })).toBeInTheDocument();
});

test("renders judge demo access panel with credentials and logs in as judge demo", async () => {
  const { onSignIn, onSignUp } = setup();
  expect(screen.getByTestId("judge-demo-panel")).toBeInTheDocument();
  expect(screen.getByText("sylvar.judges.demo@gmail.com")).toBeInTheDocument();
  expect(screen.getByText("Sylvar@Judge26")).toBeInTheDocument();

  const judgeBtn = screen.getByRole("button", { name: /login as judge demo/i });
  fireEvent.click(judgeBtn);

  await waitFor(() => {
    expect(onSignIn).toHaveBeenCalledWith("sylvar.judges.demo@gmail.com", "Sylvar@Judge26");
  });
  expect(onSignUp).not.toHaveBeenCalled();

  const emailInput = screen.getByLabelText("Email") as HTMLInputElement;
  const passwordInput = screen.getByLabelText("Password") as HTMLInputElement;
  expect(emailInput.value).toBe("sylvar.judges.demo@gmail.com");
  expect(passwordInput.value).toBe("Sylvar@Judge26");
});
