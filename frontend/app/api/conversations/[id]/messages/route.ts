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

    if (!response.ok) {
      throw new Error("Failed to fetch messages");
    }

    const data: Message[] = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch messages" },
      { status: 500 }
    );
  }
}
