// frontend/components/monitor/charts/token-line-chart.tsx
'use client';

import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, ReferenceLine } from 'recharts';

interface TokenLineChartProps {
  data: Array<{ time: string; tokens: number }>;
  current: number;
  threshold: number;
}

export function TokenLineChart({ data, current, threshold }: TokenLineChartProps) {
  const chartData = data.map((d) => ({
    ...d,
    time: new Date(d.time).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }),
  }));

  // 添加当前点
  const withCurrent = [
    ...chartData,
    { time: '当前', tokens: current },
  ];

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={withCurrent}>
          <XAxis dataKey="time" />
          <YAxis />
          <Tooltip />
          <ReferenceLine
            y={threshold}
            stroke="#ef4444"
            strokeDasharray="3 3"
            label={`阈值: ${threshold}`}
          />
          <Line
            type="monotone"
            dataKey="tokens"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
