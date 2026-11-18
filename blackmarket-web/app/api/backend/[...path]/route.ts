import { NextRequest, NextResponse } from "next/server";
import { isAuthenticated } from "@/lib/session";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };
async function proxy(request: NextRequest, context: Context) {
  if (!(await isAuthenticated())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const base = process.env.BLACKMARKET_BACKEND_URL?.replace(/\/$/, "");
  const token = process.env.BLACKMARKET_API_TOKEN;
  if (!base || !token) return NextResponse.json({ error: "Backend connection is not configured" }, { status: 503 });
  const { path } = await context.params;
  const encodedPath = path.map(encodeURIComponent).join("/");
  const target = new URL(base + (path[0] === "health" ? "/health" : "/api/" + encodedPath));
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));
  const headers = new Headers({ Authorization: "Bearer " + token, Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const init: RequestInit = { method: request.method, headers, cache: "no-store" };
  if (request.method !== "GET" && request.method !== "HEAD") init.body = await request.text();
  try {
    const upstream = await fetch(target, init);
    const contentType = upstream.headers.get("content-type") || "application/json";
    if (path[0] === "events" && upstream.ok && upstream.body) {
      return new NextResponse(upstream.body, {
        status: upstream.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache, no-transform",
          "X-Accel-Buffering": "no",
        },
      });
    }
    const text = await upstream.text();
    return new NextResponse(text, { status: upstream.status, headers: { "Content-Type": contentType, "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "Backend is unreachable" }, { status: 502 });
  }
}
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
