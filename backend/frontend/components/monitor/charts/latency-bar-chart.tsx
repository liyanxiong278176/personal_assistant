// frontend/components/monitor/charts/latency-bar-chart.tsx
'use client';

import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, LabelList } from 'recharts';

interface LatencyBarChartProps {
  data: Record<string, number>;
}

export function LatencyBarChart({ data }: LatencyBarChartProps) {
  const chartData = Object.entries(data).map(([name, value]) => ({
    name: name.replace('Strategy', ''),
    value: Math.round(value),
  }));

  if (chartData.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无延迟数据
      </div>
    );
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical">
          <XAxis type="number" />
          <YAxis type="category" dataKey="name" width={80} />
          <Tooltip formatter={(value) => [`${value}ms`, '延迟']} />
          <Bar dataKey="value" fill="#8b5cf6">
            <LabelList dataKey="value" position="right" formatter={(v) => `${v}ms`} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
