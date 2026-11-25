import { NextRequest, NextResponse } from "next/server";
import {
  communityOwnerCookie,
  communityOwnerMaxAgeSeconds,
  createCommunityOwnerToken,
  verifyCommunityOwnerToken,
} from "@/lib/community-owner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (verifyCommunityOwnerToken(request.cookies.get(communityOwnerCookie)?.value)) {
    return NextResponse.json({ ok: true });
  }

  try {
    const response = NextResponse.json({ ok: true });
    response.cookies.set(communityOwnerCookie, createCommunityOwnerToken(), {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: communityOwnerMaxAgeSeconds,
    });
    return response;
  } catch {
    return NextResponse.json(
      { error: "Browser identity signing is not configured. Set BLACKMARKET_SESSION_SECRET to a random secret of at least 32 bytes." },
      { status: 503 },
    );
  }
}
