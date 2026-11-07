import { createLatestGuard } from "./latestGuard";

test("only the most recent request is current", () => {
  const g = createLatestGuard();
  const first = g.next();
  const second = g.next();
  expect(first()).toBe(false);
  expect(second()).toBe(true);
});

test("invalidate() makes every outstanding request stale", () => {
  const g = createLatestGuard();
  const a = g.next();
  g.invalidate();
  expect(a()).toBe(false);
  const b = g.next();
  expect(b()).toBe(true);
});
