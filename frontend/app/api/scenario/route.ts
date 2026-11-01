import { NextRequest, NextResponse } from "next/server";
export async function POST(request: NextRequest) {
  const body = await request.json();
  const id = encodeURIComponent(String(body.id || ""));
  try {
    const res = await fetch(`${process.env.API_INTERNAL_URL || "http://localhost:8000"}/customers/${id}/scenario`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ listeningDays: body.listeningDays, autoRenew: body.autoRenew }),
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ error: "API unavailable" }, { status: 503 });
  }
}
