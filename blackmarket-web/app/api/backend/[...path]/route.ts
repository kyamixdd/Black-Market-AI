import { NextRequest, NextResponse } from "next/server";
import { isAuthenticated } from "@/lib/session";
import { sameOriginMutation, rateLimited, requestClientKey, readLimitedBody } from "@/lib/request-security";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };

async function readResponseLimited(response: Response, maxBytes: number): Promise<string | null> {
  if (!response.body) return "";
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        return null;
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

async function proxy(request: NextRequest, context: Context) {
  const client = requestClientKey(request);
  if (request.method !== "GET" && request.method !== "HEAD" && !sameOriginMutation(request)) {
    return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  }
  if (rateLimited("proxy:" + client, 180)) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429, headers: { "Retry-After": "60" } });
  }
  if (!(await isAuthenticated())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const configuredBase = process.env.BLACKMARKET_BACKEND_URL;
  const token = process.env.BLACKMARKET_API_TOKEN;
  if (!configuredBase || !token) return NextResponse.json({ error: "Backend connection is not configured" }, { status: 503 });
  let baseUrl: URL;
  try {
    baseUrl = new URL(configuredBase);
    if (baseUrl.username || baseUrl.password || baseUrl.search || baseUrl.hash
      || (process.env.NODE_ENV === "production" && baseUrl.protocol !== "https:")) {
      return NextResponse.json({ error: "Backend URL configuration is invalid" }, { status: 503 });
    }
  } catch {
    return NextResponse.json({ error: "Backend URL configuration is invalid" }, { status: 503 });
  }

  const { path } = await context.params;
  if (!path.length || path.some((part) => !part || part === "." || part === "..")) {
    return NextResponse.json({ error: "Invalid backend route" }, { status: 400 });
  }
  const encodedPath = path.map(encodeURIComponent).join("/");
  const target = new URL(baseUrl.toString());
  target.pathname = baseUrl.pathname.replace(/\/$/, "") + (path[0] === "health" ? "/health" : "/api/" + encodedPath);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));

  const headers = new Headers({ Authorization: "Bearer " + token, Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
    signal: AbortSignal.any([request.signal, AbortSignal.timeout(15000)]),
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    try {
      init.body = await readLimitedBody(request, 1024 * 1024);
    } catch {
      return NextResponse.json({ error: "Request body exceeds the allowed size." }, { status: 413 });
    }
  }

  try {
    const upstream = await fetch(target, init);
    if (path[0] === "events" && path[1] === "stream" && upstream.ok && upstream.body) {
      return new NextResponse(upstream.body, {
        status: upstream.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache, no-transform",
          "X-Accel-Buffering": "no",
        },
      });
    }
    if (upstream.status >= 500) {
      await upstream.body?.cancel();
      return NextResponse.json({ error: "Backend service error" }, { status: 502 });
    }
    const text = await upstream.text();
    if (Buffer.byteLength(text) > 2 * 1024 * 1024) {
      return NextResponse.json({ error: "Backend response exceeds the allowed size." }, { status: 502 });
    }
    const responseType = upstream.headers.get("content-type") || "application/json";
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": responseType, "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json({ error: "Backend is unreachable" }, { status: 502 });
  }
}
export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
