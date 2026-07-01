import { IAView } from "@/components/ia/ia-view";
import { backendFetchAdmin, type AIHistoryItem } from "@/lib/api";

async function getInitialHistory(): Promise<AIHistoryItem[]> {
  try {
    const data = await backendFetchAdmin<{ historial: AIHistoryItem[] }>("/dashboard/ai/history");
    return data.historial;
  } catch {
    return [];
  }
}

export default async function IAPage() {
  const initialHistory = await getInitialHistory();
  return <IAView initialHistory={initialHistory} />;
}
