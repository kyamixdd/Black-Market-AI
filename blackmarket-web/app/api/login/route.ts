import { NextRequest, NextResponse } from "next/server";
import { makeSession, passwordMatches, sessionCookie, sessionMaxAgeSeconds } from "@/lib/session";
import { rateLimited, sameOriginMutation, requestClientKey, readLimitedBody } from "@/lib/request-security";
export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (!sameOriginMutation(request)) return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  const client = requestClientKey(request);
  if (rateLimited("login:" + client, 8)) {
    return NextResponse.json({ error: "Too many login attempts. Try again in one minute." }, { status: 429, headers: { "Retry-After": "60" } });
  }
  let body: unknown;
  try {
    const raw = await readLimitedBody(request, 8 * 1024);
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: "Invalid login request." }, { status: 400 });
  }
  try {
    const password = typeof body === "object" && body !== null && "password" in body
      ? (body as { password?: unknown }).password : undefined;
    if (typeof password !== "string" || !passwordMatches(password)) {
      return NextResponse.json({ error: "Invalid password" }, { status: 401 });
    }
    const response = NextResponse.json({ ok: true });
    response.cookies.set(sessionCookie, makeSession(), {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: sessionMaxAgeSeconds,
    });
    return response;
  } catch {
    return NextResponse.json({ error: "Authentication is not configured correctly" }, { status: 503 });
  }
}
