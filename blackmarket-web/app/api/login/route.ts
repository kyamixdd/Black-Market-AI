import { NextRequest, NextResponse } from "next/server";
import { makeSession, passwordMatches, sessionCookie } from "@/lib/session";
import { rateLimited, sameOriginMutation } from "@/lib/request-security";
export const runtime = "nodejs";
export async function POST(request: NextRequest) {
  const client = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  if (!sameOriginMutation(request)) return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  if (rateLimited("login:" + client, 8)) return NextResponse.json({ error: "Too many login attempts. Try again in one minute." }, { status: 429, headers: { "Retry-After": "60" } });
  try {
    const body = await request.json();
    if (typeof body.password !== "string" || !passwordMatches(body.password)) {
      return NextResponse.json({ error: "Invalid password" }, { status: 401 });
    }
    const response = NextResponse.json({ ok: true });
    response.cookies.set(sessionCookie, makeSession(), {
      httpOnly: true, secure: process.env.NODE_ENV === "production",
      sameSite: "strict", path: "/", maxAge: 8 * 60 * 60
    });
    return response;
  } catch {
    return NextResponse.json({ error: "Authentication is not configured correctly" }, { status: 503 });
  }
}