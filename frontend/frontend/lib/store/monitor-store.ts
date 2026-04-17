import { create } from 'zustand';
import type {
  IntentStats,
  MemoryStats,
  ContextStats,
  MonitorMessage,
} from '../monitor-types';

interface MonitorState {
  // 连接状态
  isConnected: boolean;
  error: string | null;

  // 数据
  intentStats: IntentStats | null;
  memoryStats: MemoryStats | null;
  contextStats: ContextStats | null;

  // Actions
  setConnected: (isConnected: boolean) => void;
  setError: (error: string | null) => void;
  setIntentStats: (stats: IntentStats) => void;
  setMemoryStats: (stats: MemoryStats) => void;
  setContextStats: (stats: ContextStats) => void;
  handleMessage: (message: MonitorMessage) => void;
  reset: () => void;
}

export const useMonitorStore = create<MonitorState>((set) => ({
  isConnected: false,
  error: null,
  intentStats: null,
  memoryStats: null,
  contextStats: null,

  setConnected: (isConnected) => set({ isConnected }),

  setError: (error) => set({ error }),

  setIntentStats: (stats) => set({ intentStats: stats }),

  setMemoryStats: (stats) => set({ memoryStats: stats }),

  setContextStats: (stats) => set({ contextStats: stats }),

  handleMessage: (message) => {
    switch (message.type) {
      case 'intent_stats':
        set({ intentStats: message.data });
        break;
      case 'memory_stats':
        set({ memoryStats: message.data });
        break;
      case 'context_stats':
        set({ contextStats: message.data });
        break;
      case 'error':
        set({ error: message.data.message });
        break;
      case 'stats_update':
        // 批量更新所有数据
        set({
          intentStats: message.data.intent_stats,
          memoryStats: message.data.memory_stats,
          contextStats: message.data.context_stats,
        });
        break;
    }
  },

  reset: () => set({
    isConnected: false,
    error: null,
    intentStats: null,
    memoryStats: null,
    contextStats: null,
  }),
}));
