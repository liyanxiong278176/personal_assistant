// frontend/components/monitor/charts/promotion-feed.tsx
'use client';

interface PromotionFeedProps {
  items: Array<{
    from: string;
    to: string;
    content: string;
    time: string;
  }>;
}

export function PromotionFeed({ items }: PromotionFeedProps) {
  if (items.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无晋升记录
      </div>
    );
  }

  return (
    <div className="h-64 overflow-y-auto space-y-3">
      {items.slice(-10).reverse().map((item, index) => (
        <div
          key={`${item.time}-${index}`}
          className="relative pl-6 pb-3 border-l-2 border-purple-200"
        >
          {/* 圆点 */}
          <div className="absolute left-[-5px] top-0 w-2.5 h-2.5 rounded-full bg-purple-500" />

          {/* 内容 */}
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                {item.from}
              </span>
              <span>→</span>
              <span className="px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">
                {item.to}
              </span>
              <span>{item.time}</span>
            </div>
            <p className="text-sm line-clamp-2">{item.content}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
