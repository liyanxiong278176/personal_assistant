// frontend/components/monitor/charts/classification-path.tsx
'use client';

interface ClassificationPathProps {
  items: Array<{
    query: string;
    strategy: string;
    confidence: number;
    time: string;
  }>;
}

export function ClassificationPath({ items }: ClassificationPathProps) {
  if (items.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无分类记录
      </div>
    );
  }

  return (
    <div className="h-64 overflow-y-auto space-y-2">
      {items.slice(-10).reverse().map((item, index) => (
        <div
          key={`${item.time}-${index}`}
          className="flex items-center gap-3 p-2 rounded bg-muted/50"
        >
          <div
            className={`w-2 h-2 rounded-full shrink-0 ${
              item.confidence >= 0.8
                ? 'bg-green-500'
                : item.confidence >= 0.5
                  ? 'bg-amber-500'
                  : 'bg-red-500'
            }`}
          />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">{item.query}</div>
            <div className="text-xs text-muted-foreground flex items-center gap-2">
              <span>{item.strategy}</span>
              <span>{item.time}</span>
            </div>
          </div>
          <div className="text-sm font-mono shrink-0">
            {(item.confidence * 100).toFixed(0)}%
          </div>
        </div>
      ))}
    </div>
  );
}
