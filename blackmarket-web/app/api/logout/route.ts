import { NextResponse } from "next/server";
import { sessionCookie } from "@/lib/session";
import { sameOriginMutation } from "@/lib/request-security";
import { NextRequest } from "next/server";
export async function POST(request: NextRequest) {
  if (!sameOriginMutation(request)) return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  const response = NextResponse.json({ ok: true });
  response.cookies.set(sessionCookie, "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/", maxAge: 0 });
  return response;
}