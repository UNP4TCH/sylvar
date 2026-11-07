import { ApiError } from "./api";
import { formatApiError } from "./errors";

const problem = (over: Record<string, unknown> = {}) => ({
  type: "t", title: "Forbidden", status: 403, detail: "You are not a member of this workspace.", instance: "/x", ...over,
});

test("includes backend detail, status, code and request id", () => {
  const msg = formatApiError(new ApiError(403, problem({ code: "NOT_A_MEMBER", request_id: "req-123" }) as never));
  expect(msg).toContain("You are not a member of this workspace.");
  expect(msg).toContain("HTTP 403");
  expect(msg).toContain("code NOT_A_MEMBER");
  expect(msg).toContain("request_id req-123");
});

test("ApiError without a problem body still reports the status", () => {
  const msg = formatApiError(new ApiError(502, null));
  expect(msg).toContain("HTTP 502");
});

test("network failure (fetch TypeError) is explained, not shown as 'TypeError'", () => {
  const msg = formatApiError(new TypeError("Failed to fetch"));
  expect(msg).toContain("could not be reached");
  expect(msg).toContain("CORS");
});

test("plain Error, strings and unknown values never produce an empty message", () => {
  expect(formatApiError(new Error("boom"))).toBe("boom");
  expect(formatApiError("oops")).toBe("oops");
  expect(formatApiError({})).toBe("Unknown error");
  expect(formatApiError(undefined).length).toBeGreaterThan(0);
});
