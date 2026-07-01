import { NextResponse } from "next/server";
import { backendFetchAdmin, type AIHistoryItem } from "@/lib/api";

export async function GET(request: Request) {
  const limit = new URL(request.url).searchParams.get("limit") ?? "20";
  const data = await backendFetchAdmin<{ historial: AIHistoryItem[] }>(
    `/dashboard/ai/history?limit=${limit}`
  );
  return NextResponse.json(data);
}
