const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("auth-storage");
  if (!token) return {};
  try {
    const parsed = JSON.parse(token);
    return {
      Authorization: `Bearer ${parsed.state?.token || parsed.token}`,
    };
  } catch {
    return {};
  }
}

export interface EvalMetrics {
  intent_accuracy: number | null;
  intent_basic_accuracy: number | null;
  intent_edge_accuracy: number | null;
  intent_distribution: Record<string, number>;
  token_reduction_rate: number;
  token_avg_before: number;
  token_avg_after: number;
  overflow_count: number;
  total_trajectories: number;
  compressed_count: number;
  verification_pass_rate: number | null;
  verification_total: number;
  memory_recall_rate: number | null;
}

export interface Trajectory {
  trace_id: string;
  conversation_id: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  success: boolean;
  user_message: string;
  intent_type: string | null;
  intent_confidence: number | null;
  tokens_input: number | null;
  tokens_output: number | null;
  tokens_before_compress: number | null;
  tokens_after_compress: number | null;
  is_compressed: boolean;
  verification_score: number | null;
  verification_passed: boolean | null;
  iteration_count: number;
}

export interface ChartsData {
  token_trend: Array<{ date: string; avg_before: number; avg_after: number; count: number }>;
  intent_distribution: Array<{ name: string; value: number }>;
  daily_volume: Array<{ date: string; count: number }>;
}

export async function getEvalMetrics(days = 7): Promise<EvalMetrics> {
  const res = await fetch(`${API_BASE}/api/v1/eval/metrics?days=${days}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error("UNAUTHORIZED");
    throw new Error("Failed to fetch metrics");
  }
  const data = await res.json();
  return data.data;
}

export async function getTrajectories(days = 7, limit = 50): Promise<Trajectory[]> {
  const res = await fetch(`${API_BASE}/api/v1/eval/trajectories?days=${days}&limit=${limit}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error("UNAUTHORIZED");
    throw new Error("Failed to fetch trajectories");
  }
  const data = await res.json();
  return data.data;
}

export async function getChartsData(days = 7): Promise<ChartsData> {
  const res = await fetch(`${API_BASE}/api/v1/eval/charts?days=${days}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error("UNAUTHORIZED");
    throw new Error("Failed to fetch charts data");
  }
  const data = await res.json();
  return data.data;
}
