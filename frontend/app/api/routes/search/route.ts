import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const keywords = searchParams.get("keywords");
    const city = searchParams.get("city");
    const category = searchParams.get("category");

    if (!keywords || !city) {
      return NextResponse.json(
        { error: "Missing keywords or city" },
        { status: 400 }
      );
    }

    const url = new URL(`${BACKEND_URL}/api/routes/search-location`);
    url.searchParams.set("keywords", keywords);
    url.searchParams.set("city", city);
    if (category) {
      url.searchParams.set("category", category);
    }

    const response = await fetch(url.toString());

    if (!response.ok) {
      const error = await response.json();
      return NextResponse.json(error, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Location search error:", error);
    return NextResponse.json(
      { error: "Failed to search locations" },
      { status: 500 }
    );
  }
}
