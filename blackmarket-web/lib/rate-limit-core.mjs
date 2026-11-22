const windows = new Map();
const WINDOW_MS = 60_000;
const MAX_BUCKETS = 5_000;

export function rateLimited(key, limit, now = Date.now()) {
  const recent = (windows.get(key) ?? []).filter((stamp) => stamp > now - WINDOW_MS);
  if (recent.length >= limit) {
    windows.set(key, recent);
    return true;
  }
  recent.push(now);
  windows.set(key, recent);
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

export function requestClientKey(request) {
  const forwarded = request.headers.get("x-forwarded-for");
  const nearest = forwarded?.split(",").map((value) => value.trim()).filter(Boolean).at(-1);
  const address = request.headers.get("x-real-ip")?.trim() || nearest || "unknown";
  return address.slice(0, 128);
}
