import { NextResponse } from "next/server";
import { getHistory } from "@/lib/api";

export async function GET(request: Request) {
  const days = Number(new URL(request.url).searchParams.get("days") ?? "30");
  const data = await getHistory(days);
  return NextResponse.json(data);
}
