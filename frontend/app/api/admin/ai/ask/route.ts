import { NextResponse } from "next/server";
import { backendFetchAdmin, type AskResponse } from "@/lib/api";

export async function POST(request: Request) {
  const body = await request.json();
  const data = await backendFetchAdmin<AskResponse>("/dashboard/ai/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return NextResponse.json(data);
}
