import { NextRequest } from "next/server";

const windows = new Map<string, number[]>();
const WINDOW_MS = 60_000;
const MAX_BUCKETS = 5_000;

export function requestClientKey(request: NextRequest): string {
  // The last address is the nearest proxy-added hop; do not trust a caller-
  // controlled first X-Forwarded-For value as the rate-limit identity.
  const forwarded = request.headers.get("x-forwarded-for");
  const nearest = forwarded?.split(",").map((value) => value.trim()).filter(Boolean).at(-1);
  const address = request.headers.get("x-real-ip")?.trim() || nearest || "unknown";
  return address.slice(0, 128);
}

export function rateLimited(key: string, limit: number): boolean {
  const now = Date.now();
  const recent = (windows.get(key) ?? []).filter((stamp) => stamp > now - WINDOW_MS);
  if (recent.length >= limit) {
    windows.set(key, recent);
    return true;
  }
  recent.push(now);
  windows.set(key, recent);

  // Bound attacker-controlled key growth in a long-lived Node process.
  if (windows.size > MAX_BUCKETS) {
    for (const [bucketKey, stamps] of windows) {
      if (stamps.every((stamp) => stamp <= now - WINDOW_MS)) windows.delete(bucketKey);
      if (windows.size <= MAX_BUCKETS) break;
    }
    if (windows.size > MAX_BUCKETS) {
      const oldestKey = windows.keys().next().value;
      if (oldestKey !== undefined) windows.delete(oldestKey);
    }
  }
  return false;
}

export async function readLimitedBody(request: NextRequest, maxBytes: number): Promise<string> {
  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null) {
    const length = Number(declaredLength);
    if (!Number.isSafeInteger(length) || length < 0 || length > maxBytes) {
      throw new Error("Request body exceeds the allowed size.");
    }
  }
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        throw new Error("Request body exceeds the allowed size.");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(body);
}

export function sameOriginMutation(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).origin === request.nextUrl.origin;
  } catch { return false; }
}
