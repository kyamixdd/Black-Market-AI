import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const backend = process.env.BLACKMARKET_BACKEND_URL?.replace(/\/$/, "");
  if (!backend) {
    return NextResponse.json({ status: "unconfigured" }, { status: 503 });
  }

  try {
    const response = await fetch(backend + "/health", {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    const health: unknown = await response.json();
    if (!response.ok || typeof health !== "object" || health === null || !("database_connected" in health) || health.database_connected !== true) {
      return NextResponse.json({ status: "backend_unready" }, { status: 503 });
    }
    return NextResponse.json({ status: "ok", backend: health }, { status: 200 });
  } catch {
    return NextResponse.json({ status: "backend_unreachable" }, { status: 503 });
  }
}
