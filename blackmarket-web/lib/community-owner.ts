import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";

const COOKIE = "bm_community_owner";
const MAX_AGE = 365 * 24 * 60 * 60;

function key() {
  const value = process.env.BLACKMARKET_SESSION_SECRET;
  if (!value || Buffer.byteLength(value) < 32) throw new Error("BLACKMARKET_SESSION_SECRET must contain at least 32 bytes");
  return value;
}
function sign(id: string) {
  return createHmac("sha256", key()).update("community-owner:" + id).digest("base64url");
}
export function createCommunityOwnerToken() {
  const id = randomUUID();
  return id + "." + sign(id);
}
export function verifyCommunityOwnerToken(value?: string) {
  if (typeof value !== "string" || value.length > 256) return null;
  const [id, signature, extra] = value.split(".");
  if (extra !== undefined || !/^[a-f0-9-]{36}$/i.test(id || "") || !signature) return null;
  try {
    const expected = Buffer.from(sign(id));
    const actual = Buffer.from(signature);
    if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return null;
    return id;
  } catch {
    return null;
  }
}
export const communityOwnerCookie = COOKIE;
export const communityOwnerMaxAgeSeconds = MAX_AGE;
