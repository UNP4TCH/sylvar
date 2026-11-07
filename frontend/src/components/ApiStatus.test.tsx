import { render, screen, waitFor } from "@testing-library/react";
import ApiStatus from "./ApiStatus";

test("shows alive when the health endpoint answers", async () => {
  const f = (async () => new Response(JSON.stringify({ status: "alive" }), { status: 200 })) as typeof fetch;
  render(<ApiStatus baseUrl="http://x/api/v1" fetchImpl={f} />);
  await waitFor(() => expect(screen.getByTestId("api-status")).toHaveTextContent("alive"));
});

test("shows unreachable on network failure", async () => {
  const f = (async () => {
    throw new TypeError("network");
  }) as typeof fetch;
  render(<ApiStatus baseUrl="http://x/api/v1" fetchImpl={f} />);
  await waitFor(() => expect(screen.getByTestId("api-status")).toHaveTextContent("unreachable"));
});

test("shows unreachable on a non-alive payload", async () => {
  const f = (async () => new Response(JSON.stringify({ status: "weird" }), { status: 200 })) as typeof fetch;
  render(<ApiStatus baseUrl="http://x" fetchImpl={f} />);
  await waitFor(() => expect(screen.getByTestId("api-status")).toHaveTextContent("unreachable"));
});
