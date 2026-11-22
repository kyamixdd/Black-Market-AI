import { NextRequest, NextResponse } from "next/server";
import { sessionCookie, revokeCurrentSession } from "@/lib/session";
import { sameOriginMutation } from "@/lib/request-security";

export async function POST(request: NextRequest) {
  if (!sameOriginMutation(request)) return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  const cookie = request.cookies.get(sessionCookie)?.value;
  revokeCurrentSession(cookie);
  const response = NextResponse.json({ ok: true });
  response.cookies.set(sessionCookie, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
