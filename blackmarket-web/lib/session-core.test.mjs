import test from "node:test";
import assert from "node:assert/strict";
import { createSession, verifySession, revokeSession, hashPassword, verifyPassword } from "./session-core.mjs";

const secret = "test-only-session-secret-with-at-least-32-bytes";

test("signed session validates and expires within the configured lifetime", () => {
  const now = 1_800_000_000_000;
  const token = createSession(secret, now);
  assert.equal(verifySession(token, secret, now), true);
  assert.equal(verifySession(token, secret, now + 29 * 60 * 1000), true);
  assert.equal(verifySession(token, secret, now + 31 * 60 * 1000), false);
});

test("invalid signature and malformed session are rejected", () => {
  const token = createSession(secret);
  assert.equal(verifySession(token + "x", secret), false);
  assert.equal(verifySession("bad.token.parts", secret), false);
  assert.equal(verifySession(token, "different-test-secret-with-32-characters"), false);
  assert.equal(verifySession("x".repeat(3000), secret), false);
});

test("logout revokes a valid session and repeated revocation is harmless", () => {
  const token = createSession(secret);
  assert.equal(verifySession(token, secret), true);
  assert.equal(revokeSession(token, secret), true);
  assert.equal(verifySession(token, secret), false);
  assert.equal(revokeSession(token, secret), false);
});

test("scrypt password hash verifies only the correct password", () => {
  const encoded = hashPassword("correct horse battery staple");
  assert.match(encoded, /^scrypt\$16384\$8\$1\$/);
  assert.equal(verifyPassword("correct horse battery staple", encoded), true);
  assert.equal(verifyPassword("incorrect password", encoded), false);
  assert.equal(verifyPassword("correct horse battery staple", "plaintext-secret"), false);
});

test("password hash rejects weak input and malformed encodings", () => {
  assert.throws(() => hashPassword("short"));
  assert.equal(verifyPassword("anything", "scrypt$bad$format"), false);
});
