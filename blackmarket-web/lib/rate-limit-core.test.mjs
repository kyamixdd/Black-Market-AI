import test from "node:test";
import assert from "node:assert/strict";
import { rateLimited, requestClientKey } from "./rate-limit-core.mjs";

test("rate limiter rejects requests beyond configured limit and resets after window", () => {
  const key = "security-test-" + crypto.randomUUID();
  const now = 1_900_000_000_000;
  assert.equal(rateLimited(key, 2, now), false);
  assert.equal(rateLimited(key, 2, now + 1), false);
  assert.equal(rateLimited(key, 2, now + 2), true);
  assert.equal(rateLimited(key, 2, now + 61_001), false);
});

test("client key uses nearest forwarded hop and caps key length", () => {
  const request = { headers: { get: (name) => name === "x-forwarded-for" ? "spoofed, proxy-added" : null } };
  assert.equal(requestClientKey(request), "proxy-added");
  const oversized = { headers: { get: (name) => name === "x-real-ip" ? "a".repeat(200) : null } };
  assert.equal(requestClientKey(oversized).length, 128);
});
