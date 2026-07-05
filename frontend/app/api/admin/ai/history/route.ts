import { NextResponse } from "next/server";
import { backendFetchAdmin, type AIHistoryItem } from "@/lib/api";

export async function GET(request: Request) {
  const limit = new URL(request.url).searchParams.get("limit") ?? "20";
  const userId = request.headers.get("x-user-id") ?? "";
  const data = await backendFetchAdmin<{ historial: AIHistoryItem[] }>(
    `/dashboard/ai/history?limit=${limit}`,
    { headers: { "X-User-Id": userId } }
  );
  return NextResponse.json(data);
}

export async function DELETE(request: Request) {
  const id = new URL(request.url).searchParams.get("id");
  const userId = request.headers.get("x-user-id") ?? "";
  if (!id) return NextResponse.json({ error: "id requerido" }, { status: 400 });
  const data = await backendFetchAdmin<{ ok: boolean }>(
    `/dashboard/ai/history/${id}`,
    { method: "DELETE", headers: { "X-User-Id": userId } }
  );
  return NextResponse.json(data);
}
