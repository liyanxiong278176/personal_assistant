"use client";

import type { StageInfo } from "@/lib/types";
import { Loader2, Search, Database, Filter, Wrench, Layers, Sparkles, Minus } from "lucide-react";

interface PhaseIndicatorProps {
  currentStage: StageInfo | null;
  isLoading: boolean;
  stageStates?: Record<string, "completed" | "skipped" | "pending">;
}

// 阶段中文名称映射（8 个完整阶段）
const STAGE_NAMES: Record<string, string> = {
  "1_INTENT": "意图识别",
  "2_STORAGE": "加载历史",
  "3_CTX_CLEAN": "前置清理",
  "4_TOOLS": "工具调用",
  "5_CONTEXT": "上下文构建",
  "6_LLM": "LLM生成",
  "7_CTX_MANAGE": "后置管理",
  "8_MEMORY": "记忆更新",
};

// 阶段图标映射
const STAGE_ICONS: Record<string, React.ReactNode> = {
  "1_INTENT": <Search className="w-4 h-4" />,
  "2_STORAGE": <Database className="w-4 h-4" />,
  "3_CTX_CLEAN": <Filter className="w-4 h-4" />,
  "4_TOOLS": <Wrench className="w-4 h-4" />,
  "5_CONTEXT": <Layers className="w-4 h-4" />,
  "6_LLM": <Sparkles className="w-4 h-4" />,
  "7_CTX_MANAGE": <Layers className="w-4 h-4" />,
  "8_MEMORY": <Database className="w-4 h-4" />,
};

// 阶段顺序和进度映射（8 个完整阶段）
const STAGE_ORDER = [
  "1_INTENT",
  "2_STORAGE",
  "3_CTX_CLEAN",
  "4_TOOLS",
  "5_CONTEXT",
  "6_LLM",
  "7_CTX_MANAGE",
  "8_MEMORY",
];

export function PhaseIndicator({ currentStage, isLoading, stageStates = {} }: PhaseIndicatorProps) {
  // 工作流程完成后仍然显示，只要有 stageStates 或 currentStage
  const hasActivity = isLoading || currentStage || Object.keys(stageStates).length > 0;
  if (!hasActivity) return null;

  // 计算进度 - 使用最后一个完成的阶段
  let currentIndex = -1;
  if (currentStage) {
    currentIndex = STAGE_ORDER.indexOf(currentStage.name);
  } else {
    // 如果没有当前阶段，找到最后一个完成的阶段
    for (let i = STAGE_ORDER.length - 1; i >= 0; i--) {
      if (stageStates[STAGE_ORDER[i]]) {
        currentIndex = i;
        break;
      }
    }
  }
  const progress = currentIndex >= 0 ? ((currentIndex + 1) / STAGE_ORDER.length) * 100 : 0;

  // 确定显示的状态信息
  const displayLabel = currentStage?.label || "工作流程完成";
  const displayMessage = currentStage?.status === "skip"
    ? "已跳过"
    : currentStage?.message || "所有阶段已完成";

  return (
    <div className="sticky top-0 z-50 bg-background/95 backdrop-blur-sm border-b border-border/50">
      <div className="max-w-4xl mx-auto px-4 py-3">
        <div className="bg-card/80 border border-border/50 rounded-xl p-3 backdrop-blur-sm">
          {/* 阶段列表 */}
          <div className="flex items-center justify-between mb-2">
            {STAGE_ORDER.map((stageName, index) => {
              const isActive = currentStage?.name === stageName;
              const stageState = stageStates[stageName];
              const isCompleted = stageState === "completed";
              const isSkipped = stageState === "skipped";
              const isPending = stageState === "pending";
              const isWorking = isActive || isPending;
              const icon = STAGE_ICONS[stageName];
              const displayName = STAGE_NAMES[stageName] || stageName;

              return (
                <div
                  key={stageName}
                  className={`flex flex-col items-center gap-1 transition-all duration-300 ${
                    isWorking ? "scale-110" : ""
                  }`}
                >
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center transition-all duration-300 ${
                      isSkipped
                        ? "bg-yellow-500/20 text-yellow-600 border border-yellow-500/50"
                        : isCompleted
                        ? "bg-green-500/20 text-green-500"
                        : isWorking
                        ? "bg-gradient-to-br from-primary to-accent text-white shadow-lg shadow-primary/30"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {isSkipped ? (
                      <Minus className="w-3.5 h-3.5" />
                    ) : isCompleted ? (
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : isWorking ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      icon
                    )}
                  </div>
                  <span
                    className={`text-[10px] transition-colors leading-tight ${
                      isWorking
                        ? "text-primary font-medium"
                        : isSkipped
                        ? "text-yellow-600"
                        : isCompleted
                        ? "text-green-500"
                        : "text-muted-foreground/50"
                    }`}
                  >
                    {displayName}
                  </span>
                </div>
              );
            })}
          </div>

          {/* 进度条 */}
          <div className="relative h-1.5 bg-muted rounded-full overflow-hidden mb-2">
            <div
              className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary to-accent rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
            {/* 发光效果 */}
            <div
              className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary/50 to-accent/50 rounded-full blur-sm transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>

          {/* 当前阶段描述 */}
          <div className="flex items-center gap-2 text-xs">
            <span className="text-primary font-medium">{displayLabel}</span>
            <span className="text-muted-foreground">{displayMessage}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
