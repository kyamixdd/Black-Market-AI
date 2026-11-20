import { NextRequest } from "next/server";

const windows = new Map<string, number[]>();
const WINDOW_MS = 60_000;
export function rateLimited(key: string, limit: number): boolean {
  const now = Date.now();
  const recent = (windows.get(key) ?? []).filter((stamp) => stamp > now - WINDOW_MS);
  if (recent.length >= limit) { windows.set(key, recent); return true; }
  recent.push(now); windows.set(key, recent);
  return false;
}

export function sameOriginMutation(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).origin === request.nextUrl.origin;
  } catch { return false; }
}
