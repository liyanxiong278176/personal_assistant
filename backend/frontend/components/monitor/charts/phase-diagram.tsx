// frontend/components/monitor/charts/phase-diagram.tsx
'use client';

interface PhaseDiagramProps {
  currentPhase: 'pre_clean' | 'guard' | 'compress' | 'idle';
}

const PHASES = [
  { key: 'pre_clean', label: '前置清理', color: 'bg-blue-500' },
  { key: 'guard', label: '守卫检查', color: 'bg-amber-500' },
  { key: 'compress', label: '压缩处理', color: 'bg-purple-500' },
  { key: 'idle', label: '空闲', color: 'bg-gray-400' },
] as const;

export function PhaseDiagram({ currentPhase }: PhaseDiagramProps) {
  const currentIndex = PHASES.findIndex((p) => p.key === currentPhase);

  return (
    <div className="h-64 flex items-center justify-center">
      <div className="w-full max-w-md">
        {/* 阶段流程 */}
        <div className="relative">
          {/* 进度条背景 */}
          <div className="absolute top-4 left-0 right-0 h-1 bg-muted" />

          {/* 阶段节点 */}
          <div className="relative flex justify-between">
            {PHASES.map((phase, index) => (
              <div
                key={phase.key}
                className="flex flex-col items-center gap-2"
              >
                {/* 节点圆圈 */}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium z-10 ${
                    index === currentIndex
                      ? phase.color
                      : index < currentIndex
                        ? 'bg-green-500'
                        : 'bg-gray-300'
                  }`}
                >
                  {index + 1}
                </div>

                {/* 标签 */}
                <div className="text-xs text-center">
                  <div className="font-medium">{phase.label}</div>
                  {index === currentIndex && (
                    <div className="text-amber-600">进行中</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 当前状态说明 */}
        <div className="mt-8 text-center">
          <div className="text-sm text-muted-foreground">当前阶段</div>
          <div className="text-lg font-semibold">
            {PHASES[currentIndex]?.label || '未知'}
          </div>
        </div>
      </div>
    </div>
  );
}
