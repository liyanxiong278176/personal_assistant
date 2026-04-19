// frontend/components/monitor/charts/memory-list.tsx
'use client';

interface MemoryListProps {
  items: Array<{
    level: string;
    type: string;
    content: string;
    importance: number;
  }>;
}

const TYPE_COLORS: Record<string, string> = {
  fact: 'bg-blue-100 text-blue-700',
  preference: 'bg-green-100 text-green-700',
  intent: 'bg-purple-100 text-purple-700',
  constraint: 'bg-orange-100 text-orange-700',
};

export function MemoryList({ items }: MemoryListProps) {
  if (items.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-muted-foreground">
        暂无记忆
      </div>
    );
  }

  return (
    <div className="h-64 overflow-y-auto space-y-2">
      {items.slice(-10).map((item, index) => (
        <div
          key={`${item.level}-${item.type}-${index}`}
          className="p-3 rounded bg-muted/50 hover:bg-muted transition-colors"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`px-1.5 py-0.5 rounded text-xs ${
                    TYPE_COLORS[item.type] || 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {item.type}
                </span>
                <span className="text-xs text-muted-foreground">
                  {(item.importance * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm line-clamp-2">{item.content}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
