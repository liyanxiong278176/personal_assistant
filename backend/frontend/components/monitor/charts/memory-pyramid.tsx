// frontend/components/monitor/charts/memory-pyramid.tsx
'use client';

interface MemoryPyramidProps {
  data: {
    working: number;
    episodic: number;
    semantic: number;
  };
}

export function MemoryPyramid({ data }: MemoryPyramidProps) {
  const max = Math.max(data.semantic, data.episodic, data.working, 1);

  return (
    <div className="h-64 flex flex-col items-center justify-center gap-4">
      {/* 语义记忆 - 顶层 */}
      <div className="w-full max-w-xs">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="font-medium">语义记忆</span>
          <span className="text-muted-foreground">{data.semantic} 条</span>
        </div>
        <div className="h-12 bg-gradient-to-r from-purple-500 to-purple-600 rounded-t-lg flex items-center justify-center text-white font-medium relative overflow-hidden group">
          <div
            className="absolute inset-y-0 left-0 bg-white/20 transition-all duration-500"
            style={{ width: `${(data.semantic / max) * 100}%` }}
          />
          <span className="relative z-10">长期偏好</span>
        </div>
      </div>

      {/* 情景记忆 - 中层 */}
      <div className="w-full max-w-md">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="font-medium">情景记忆</span>
          <span className="text-muted-foreground">{data.episodic} 条</span>
        </div>
        <div className="h-12 bg-gradient-to-r from-blue-500 to-blue-600 flex items-center justify-center text-white font-medium relative overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-white/20 transition-all duration-500"
            style={{ width: `${(data.episodic / max) * 100}%` }}
          />
          <span className="relative z-10">当前对话</span>
        </div>
      </div>

      {/* 工作记忆 - 底层 */}
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="font-medium">工作记忆</span>
          <span className="text-muted-foreground">{data.working} 条</span>
        </div>
        <div className="h-12 bg-gradient-to-r from-green-500 to-green-600 rounded-b-lg flex items-center justify-center text-white font-medium relative overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-white/20 transition-all duration-500"
            style={{ width: `${(data.working / max) * 100}%` }}
          />
          <span className="relative z-10">最近消息</span>
        </div>
      </div>
    </div>
  );
}
