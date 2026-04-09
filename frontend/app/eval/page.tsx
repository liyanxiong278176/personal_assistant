"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/lib/store/auth-store";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from "recharts";
import { evalApi } from "@/lib/api/eval";
import type { EvalMetrics, Trajectory, ChartsData } from "@/lib/api/eval";

// Intent color mapping
const INTENT_COLORS: Record<string, string> = {
  itinerary: "#2563eb",
  weather: "#22c55e",
  transport: "#f59e0b",
  hotel: "#8b5cf6",
  query: "#ec4899",
  chat: "#6b7280",
  image: "#14b8a6",
  preference: "#f97316",
  unknown: "#9ca3af",
};

const PIE_COLORS = ["#2563eb", "#22c55e", "#f59e0b", "#8b5cf6", "#ec4899", "#6b7280", "#14b8a6", "#f97316"];

function MetricCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className="card-journal p-5 text-center">
      <div className={`text-3xl font-bold ${highlight ? "text-gradient-warm" : "text-foreground"}`}>
        {value}
      </div>
      <div className="text-sm text-muted-foreground mt-1">{label}</div>
      {sub && <div className="text-xs text-muted-foreground/60 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function EvalPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const [metrics, setMetrics] = useState<EvalMetrics | null>(null);
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [charts, setCharts] = useState<ChartsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(7);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [m, t, c] = await Promise.all([
        evalApi.getMetrics(days),
        evalApi.getTrajectories(days, 20),
        evalApi.getChartsData(days),
      ]);
      setMetrics(m);
      setTrajectories(t);
      setCharts(c);
    } catch (e: any) {
      if (e.message === "UNAUTHORIZED") {
        setError("请先登录后再查看评估数据");
      } else {
        setError(`加载失败: ${e.message}`);
      }
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      loadData();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, authLoading, loadData]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-atmosphere flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-4">
          <div className="card-journal p-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center">
              <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h2 className="font-display text-2xl mb-2">评估体系</h2>
            <p className="text-muted-foreground text-sm">登录后查看您的 AI Agent 评估指标</p>
            <a
              href="/chat"
              className="mt-6 inline-flex items-center justify-center px-6 py-2.5 btn-primary text-sm"
            >
              返回聊天
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-atmosphere">
      {/* Header */}
      <header className="h-14 border-b border-border/50 glass-card/30 flex items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <a href="/chat" className="p-2 hover:bg-muted/60 rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </a>
          <h1 className="font-display text-xl font-semibold text-gradient-warm">评估体系</h1>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="input-premium text-sm py-1.5 px-3"
          >
            <option value={7}>近 7 天</option>
            <option value={14}>近 14 天</option>
            <option value={30}>近 30 天</option>
          </select>
          <button onClick={loadData} disabled={loading} className="btn-ghost-premium text-xs px-3 py-1.5">
            {loading ? "加载中..." : "刷新"}
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : metrics ? (
          <>
            {/* Metrics cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
              <MetricCard
                label="总轨迹数"
                value={metrics.total_trajectories.toString()}
                sub={`压缩 ${metrics.compressed_count} 条`}
              />
              <MetricCard
                label="Token 降低率"
                value={metrics.token_reduction_rate > 0 ? `${metrics.token_reduction_rate.toFixed(1)}%` : "--"}
                sub={metrics.token_avg_before > 0 ? `${metrics.token_avg_before} → ${metrics.token_avg_after}` : ""}
              />
              <MetricCard
                label="超限次数"
                value={metrics.overflow_count.toString()}
                sub={`近 ${days} 天`}
              />
              <MetricCard
                label="验证通过率"
                value={metrics.verification_pass_rate !== null ? `${metrics.verification_pass_rate.toFixed(0)}%` : "--"}
                sub={`${metrics.verification_total} 次验证`}
              />
              <MetricCard
                label="意图分布"
                value={Object.keys(metrics.intent_distribution || {}).length.toString()}
                sub="种意图类型"
              />
            </div>

            {/* Charts area */}
            {charts && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
                {/* Token compression trend */}
                <div className="card-journal p-5">
                  <h3 className="font-display text-lg mb-4">Token 压缩趋势</h3>
                  {charts.token_trend.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={charts.token_trend}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 11 }}
                          stroke="hsl(var(--muted-foreground))"
                        />
                        <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                        <Tooltip
                          contentStyle={{
                            background: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "0.75rem",
                          }}
                        />
                        <Legend />
                        <Line type="monotone" dataKey="avg_before" stroke="#ef4444" name="压缩前" dot={false} />
                        <Line type="monotone" dataKey="avg_after" stroke="#22c55e" name="压缩后" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[200px] flex items-center justify-center text-muted-foreground/60 text-sm">
                      暂无数据
                    </div>
                  )}
                </div>

                {/* Intent distribution pie chart */}
                <div className="card-journal p-5">
                  <h3 className="font-display text-lg mb-4">意图类型分布</h3>
                  {charts.intent_distribution.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={charts.intent_distribution}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={80}
                          dataKey="value"
                          nameKey="name"
                          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                          labelLine={false}
                        >
                          {charts.intent_distribution.map((_, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            background: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "0.75rem",
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[200px] flex items-center justify-center text-muted-foreground/60 text-sm">
                      暂无数据
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Trajectory table */}
            {trajectories.length > 0 && (
              <div className="card-journal p-5">
                <h3 className="font-display text-lg mb-4">最近轨迹</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/50">
                        <th className="text-left py-2 px-3 text-muted-foreground font-medium">时间</th>
                        <th className="text-left py-2 px-3 text-muted-foreground font-medium">意图</th>
                        <th className="text-left py-2 px-3 text-muted-foreground font-medium">消息</th>
                        <th className="text-right py-2 px-3 text-muted-foreground font-medium">Token</th>
                        <th className="text-right py-2 px-3 text-muted-foreground font-medium">耗时</th>
                        <th className="text-right py-2 px-3 text-muted-foreground font-medium">状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trajectories.map((t) => (
                        <tr key={t.trace_id} className="border-b border-border/30 hover:bg-muted/20">
                          <td className="py-2 px-3 text-xs text-muted-foreground">
                            {t.started_at ? new Date(t.started_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : ""}
                          </td>
                          <td className="py-2 px-3">
                            {t.intent_type ? (
                              <span
                                className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                                style={{
                                  background: `${INTENT_COLORS[t.intent_type] || INTENT_COLORS.unknown}20`,
                                  color: INTENT_COLORS[t.intent_type] || INTENT_COLORS.unknown,
                                }}
                              >
                                {t.intent_type}
                              </span>
                            ) : (
                              <span className="text-muted-foreground/40">--</span>
                            )}
                          </td>
                          <td className="py-2 px-3 max-w-[200px] truncate text-xs">
                            {t.user_message || "--"}
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-xs">
                            {t.tokens_input !== null ? `${t.tokens_input}` : "--"}
                            {t.tokens_output !== null ? ` / ${t.tokens_output}` : ""}
                          </td>
                          <td className="py-2 px-3 text-right text-xs text-muted-foreground">
                            {t.duration_ms !== null ? `${t.duration_ms}ms` : "--"}
                          </td>
                          <td className="py-2 px-3 text-right">
                            {t.success ? (
                              <span className="text-xs text-green-600 dark:text-green-400">成功</span>
                            ) : (
                              <span className="text-xs text-red-500">失败</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="card-journal p-12 text-center">
            <p className="text-muted-foreground">暂无评估数据，请先与 AI 对话产生轨迹</p>
          </div>
        )}
      </div>
    </div>
  );
}
