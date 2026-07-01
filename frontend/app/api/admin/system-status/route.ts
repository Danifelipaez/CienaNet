import { NextResponse } from "next/server";
import { backendFetchAdmin, type SystemStatusResponse } from "@/lib/api";

export async function GET() {
  const data = await backendFetchAdmin<SystemStatusResponse>("/dashboard/system-status");
  return NextResponse.json(data);
}
