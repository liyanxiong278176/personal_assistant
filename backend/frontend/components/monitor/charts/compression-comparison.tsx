// frontend/components/monitor/charts/compression-comparison.tsx
'use client';

interface CompressionComparisonProps {
  before: { messages: number; tokens: number };
  after: { messages: number; tokens: number };
}

export function CompressionComparison({
  before,
  after,
}: CompressionComparisonProps) {
  const messageReduction = ((before.messages - after.messages) / before.messages) * 100;
  const tokenReduction = ((before.tokens - after.tokens) / before.tokens) * 100;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* 压缩前 */}
        <div className="p-4 rounded bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800">
          <div className="text-sm text-red-700 dark:text-red-300 font-medium mb-2">压缩前</div>
          <div className="text-2xl font-bold text-red-900 dark:text-red-100">
            {before.messages} 条
          </div>
          <div className="text-sm text-red-600 dark:text-red-400">
            {before.tokens} tokens
          </div>
        </div>

        {/* 压缩后 */}
        <div className="p-4 rounded bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800">
          <div className="text-sm text-green-700 dark:text-green-300 font-medium mb-2">压缩后</div>
          <div className="text-2xl font-bold text-green-900 dark:text-green-100">
            {after.messages} 条
          </div>
          <div className="text-sm text-green-600 dark:text-green-400">
            {after.tokens} tokens
          </div>
        </div>
      </div>

      {/* 压缩效果 */}
      <div className="p-4 rounded bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800">
        <div className="text-sm text-blue-700 dark:text-blue-300 font-medium mb-2">压缩效果</div>
        <div className="flex gap-4">
          <div>
            <span className="text-2xl font-bold text-blue-900 dark:text-blue-100">
              {messageReduction.toFixed(1)}%
            </span>
            <span className="text-sm text-blue-600 dark:text-blue-400 ml-1">消息减少</span>
          </div>
          <div>
            <span className="text-2xl font-bold text-blue-900 dark:text-blue-100">
              {tokenReduction.toFixed(1)}%
            </span>
            <span className="text-sm text-blue-600 dark:text-blue-400 ml-1">Token 减少</span>
          </div>
        </div>
      </div>
    </div>
  );
}
