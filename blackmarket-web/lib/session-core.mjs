import { createHmac, timingSafeEqual, randomBytes, randomUUID, scryptSync } from "node:crypto";

const SESSION_TTL_SECONDS = 30 * 60;
const CLOCK_SKEW_SECONDS = 30;
const revoked = new Map();
const REVOCATION_LIMIT = 10_000;

function signingKey(secret) {
  if (typeof secret !== "string" || Buffer.byteLength(secret) < 32) {
    throw new Error("BLACKMARKET_SESSION_SECRET must contain at least 32 bytes");
  }
  return secret;
}
function sign(payload, secret) {
  return createHmac("sha256", signingKey(secret)).update(payload).digest("base64url");
}
function pruneRevocations(now) {
  for (const [id, exp] of revoked) if (exp <= now) revoked.delete(id);
  while (revoked.size > REVOCATION_LIMIT) revoked.delete(revoked.keys().next().value);
}

export function createSession(secret, nowMs = Date.now()) {
  const now = Math.floor(nowMs / 1000);
  const payload = Buffer.from(JSON.stringify({ iat: now, exp: now + SESSION_TTL_SECONDS, jti: randomUUID() })).toString("base64url");
  return payload + "." + sign(payload, secret);
}

export function verifySession(value, secret, nowMs = Date.now()) {
  if (typeof value !== "string" || value.length > 2048) return false;
  const parts = value.split(".");
  if (parts.length !== 2 || !parts[0] || !parts[1]) return false;
  let expected;
  try { expected = Buffer.from(sign(parts[0], secret)); } catch { return false; }
  const actual = Buffer.from(parts[1]);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return false;
  try {
    const data = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
    const now = Math.floor(nowMs / 1000);
    if (!Number.isSafeInteger(data.iat) || data.iat > now + CLOCK_SKEW_SECONDS
      || data.iat < now - SESSION_TTL_SECONDS - CLOCK_SKEW_SECONDS
      || !Number.isSafeInteger(data.exp) || data.exp <= now
      || data.exp > data.iat + SESSION_TTL_SECONDS
      || typeof data.jti !== "string" || data.jti.length < 16) return false;
    pruneRevocations(now);
    return !revoked.has(data.jti);
  } catch { return false; }
}

export function revokeSession(value, secret, nowMs = Date.now()) {
  if (!verifySession(value, secret, nowMs)) return false;
  try {
    const payload = value.split(".")[0];
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    revoked.set(data.jti, data.exp);
    pruneRevocations(Math.floor(nowMs / 1000));
    return true;
  } catch { return false; }
}

export function hashPassword(password) {
  if (typeof password !== "string" || password.length < 12 || password.length > 1024) {
    throw new Error("Password must contain 12–1024 characters.");
  }
  const salt = randomBytes(16);
  const hash = scryptSync(password, salt, 64, { N: 16384, r: 8, p: 1, maxmem: 64 * 1024 * 1024 });
  return ["scrypt", "16384", "8", "1", salt.toString("base64url"), hash.toString("base64url")].join("$");
}

export function verifyPassword(password, encoded) {
  if (typeof password !== "string" || typeof encoded !== "string" || password.length > 1024) return false;
  const parts = encoded.split("$");
  if (parts.length !== 6 || parts[0] !== "scrypt" || parts[1] !== "16384" || parts[2] !== "8" || parts[3] !== "1") return false;
  try {
    const salt = Buffer.from(parts[4], "base64url");
    const expected = Buffer.from(parts[5], "base64url");
    if (salt.length !== 16 || expected.length !== 64) return false;
    const actual = scryptSync(password, salt, 64, { N: 16384, r: 8, p: 1, maxmem: 64 * 1024 * 1024 });
    return timingSafeEqual(actual, expected);
  } catch { return false; }
}
