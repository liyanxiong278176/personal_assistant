import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { locations, city, strategy = 10 } = body;

    if (!locations || locations.length < 2) {
      return NextResponse.json(
        { error: "At least 2 locations required" },
        { status: 400 }
      );
    }

    const response = await fetch(`${BACKEND_URL}/api/routes/multi-point`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locations, city, strategy }),
    });

    if (!response.ok) {
      const error = await response.json();
      return NextResponse.json(error, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Multi-point route error:", error);
    return NextResponse.json(
      { error: "Failed to plan route" },
      { status: 500 }
    );
  }
}
