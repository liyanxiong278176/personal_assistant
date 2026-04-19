// frontend/components/monitor/charts/confidence-bar-chart.tsx
'use client';

import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, Cell } from 'recharts';

interface ConfidenceBarChartProps {
  data: {
    high: number;
    mid: number;
    low: number;
  };
}

export function ConfidenceBarChart({ data }: ConfidenceBarChartProps) {
  const chartData = [
    { name: '高 (≥0.8)', value: data.high, color: '#22c55e' },
    { name: '中 (0.5-0.8)', value: data.mid, color: '#f59e0b' },
    { name: '低 (<0.5)', value: data.low, color: '#ef4444' },
  ];

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="value">
            {chartData.map((entry) => (
              <Cell key={`cell-${entry.name}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
