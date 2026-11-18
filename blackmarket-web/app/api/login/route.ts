import { NextRequest, NextResponse } from "next/server";
import { makeSession, passwordMatches, sessionCookie } from "@/lib/session";
export const runtime = "nodejs";
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    if (typeof body.password !== "string" || !passwordMatches(body.password)) {
      return NextResponse.json({ error: "Invalid password" }, { status: 401 });
    }
    const response = NextResponse.json({ ok: true });
    response.cookies.set(sessionCookie, makeSession(), {
      httpOnly: true, secure: process.env.NODE_ENV === "production",
      sameSite: "lax", path: "/", maxAge: 8 * 60 * 60
    });
    return response;
  } catch {
    return NextResponse.json({ error: "Authentication is not configured correctly" }, { status: 503 });
  }
}