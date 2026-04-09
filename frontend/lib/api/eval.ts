const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuthHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("auth-storage")
    ? JSON.parse(localStorage.getItem("auth-storage")!).state.token
    : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Evaluation metrics returned by the eval API
 */
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

/**
 * A single trajectory record from the eval system
 */
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

/**
 * Chart data for visualizations
 */
export interface ChartsData {
  token_trend: Array<{ date: string; avg_before: number; avg_after: number; count: number }>;
  intent_distribution: Array<{ name: string; value: number }>;
  daily_volume: Array<{ date: string; count: number }>;
}

/**
 * API response wrapper for eval endpoints
 */
interface EvalApiResponse<T> {
  status: string;
  data: T;
}

async function handleEvalResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("UNAUTHORIZED");
    }
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }
  const result = (await response.json()) as EvalApiResponse<T>;
  return result.data;
}

export const evalApi = {
  /**
   * Get evaluation metrics for a time period
   * @param days - Number of days to look back (default: 7)
   * @returns Evaluation metrics including accuracy, token stats, and memory metrics
   */
  async getMetrics(days = 7): Promise<EvalMetrics> {
    const response = await fetch(`${API_BASE}/api/v1/eval/metrics?days=${days}`, {
      headers: getAuthHeaders(),
    });
    return handleEvalResponse<EvalMetrics>(response);
  },

  /**
   * Get trajectory records for a time period
   * @param days - Number of days to look back (default: 7)
   * @param limit - Maximum number of records to return (default: 50)
   * @returns Array of trajectory records
   */
  async getTrajectories(days = 7, limit = 50): Promise<Trajectory[]> {
    const response = await fetch(
      `${API_BASE}/api/v1/eval/trajectories?days=${days}&limit=${limit}`,
      {
        headers: getAuthHeaders(),
      }
    );
    return handleEvalResponse<Trajectory[]>(response);
  },

  /**
   * Get chart data for visualizations
   * @param days - Number of days to look back (default: 7)
   * @returns Chart data including token trends, intent distribution, and daily volume
   */
  async getChartsData(days = 7): Promise<ChartsData> {
    const response = await fetch(`${API_BASE}/api/v1/eval/charts?days=${days}`, {
      headers: getAuthHeaders(),
    });
    return handleEvalResponse<ChartsData>(response);
  },
};
