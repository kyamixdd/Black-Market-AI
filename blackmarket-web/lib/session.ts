import { cookies } from "next/headers";
import { createSession, verifySession, revokeSession, verifyPassword } from "./session-core.mjs";

const COOKIE = "bm_session";
function secret() {
  const value = process.env.BLACKMARKET_SESSION_SECRET;
  if (!value || Buffer.byteLength(value) < 32) throw new Error("BLACKMARKET_SESSION_SECRET must contain at least 32 bytes");
  return value;
}
export function passwordMatches(candidate: string) {
  const encoded = process.env.BLACKMARKET_WEB_PASSWORD_HASH;
  if (!encoded) throw new Error("BLACKMARKET_WEB_PASSWORD_HASH is not configured");
  return verifyPassword(candidate, encoded);
}
export function makeSession() {
  return createSession(secret());
}
export function validSession(value?: string) {
  try { return verifySession(value, secret()); } catch { return false; }
}
export function revokeCurrentSession(value?: string) {
  try { return revokeSession(value, secret()); } catch { return false; }
}
export async function isAuthenticated() {
  const jar = await cookies();
  return validSession(jar.get(COOKIE)?.value);
}
export const sessionCookie = COOKIE;
export const sessionMaxAgeSeconds = 30 * 60;
