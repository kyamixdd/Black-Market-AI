import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

const COOKIE = "bm_session";
const ttl = 8 * 60 * 60;
const clockSkewSeconds = 30;

function secret() {
  const value = process.env.BLACKMARKET_SESSION_SECRET;
  if (!value || value.length < 32) throw new Error("BLACKMARKET_SESSION_SECRET must contain at least 32 characters");
  return value;
}
function sign(value: string) {
  return createHmac("sha256", secret()).update(value).digest("base64url");
}
export function passwordMatches(candidate: string) {
  const expected = process.env.BLACKMARKET_WEB_PASSWORD;
  if (!expected) throw new Error("BLACKMARKET_WEB_PASSWORD is not configured");
  const a = Buffer.from(candidate);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}
export function makeSession() {
  const payload = Buffer.from(JSON.stringify({ iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + ttl, nonce: crypto.randomUUID() })).toString("base64url");
  return payload + "." + sign(payload);
}
export function validSession(value?: string) {
  if (!value) return false;
  const [payload, signature] = value.split(".");
  if (!payload || !signature) return false;
  const expected = Buffer.from(sign(payload));
  const actual = Buffer.from(signature);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return false;
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    const now = Math.floor(Date.now() / 1000);
    return Number.isFinite(data.iat) && data.iat <= now + clockSkewSeconds
      && data.iat >= now - ttl - clockSkewSeconds
      && Number.isFinite(data.exp) && data.exp > now
      && data.exp <= data.iat + ttl
      && typeof data.nonce === "string" && data.nonce.length >= 16;
  } catch { return false; }
}
export async function isAuthenticated() {
  const jar = await cookies();
  return validSession(jar.get(COOKIE)?.value);
}
export const sessionCookie = COOKIE;
