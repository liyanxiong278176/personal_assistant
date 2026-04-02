import { NextResponse } from "next/server";
import type { Message } from "../../../../../../shared/types";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const response = await fetch(`${BACKEND_URL}/api/conversations/${id}/messages`, {
      method: "GET",
    });

    // Return 404 from backend directly (conversation not found)
    if (response.status === 404) {
      return NextResponse.json([], { status: 200 });  // Return empty array as 200
    }

    if (!response.ok) {
      const errorText = await response.text();
      console.error("API error:", response.status, errorText);
      throw new Error(`Failed to fetch messages: ${response.status}`);
    }

    const data: Message[] = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("API error:", error);
    // Return empty array instead of error to gracefully handle deleted conversations
    return NextResponse.json([]);
  }
}
