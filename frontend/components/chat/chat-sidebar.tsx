"use client";

import { ConversationList } from "@/components/conversations/conversation-list";
import { useAuthStore } from "@/lib/store/auth-store";
import { Compass } from "lucide-react";

interface ChatSidebarProps {
  onClose?: () => void;
  onConversationSelect?: (id: string) => void;
  onNewConversation?: () => void;
}

export function ChatSidebar({ onClose, onConversationSelect, onNewConversation }: ChatSidebarProps) {
  const { isAuthenticated } = useAuthStore();

  return (
    <div className="h-full flex flex-col bg-card/50">
      {isAuthenticated ? (
        <ConversationList
          onNewConversation={onNewConversation}
          onConversationSelect={onConversationSelect}
        />
      ) : (
        <>
          {/* Header */}
          <div className="h-14 border-b border-border/40 flex items-center justify-between px-4">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
                <Compass className="w-4 h-4 text-white" />
              </div>
              <h2 className="font-display font-semibold text-sm text-foreground/80">对话历史</h2>
            </div>
            {onClose && (
              <button
                onClick={onClose}
                className="p-1.5 hover:bg-muted/60 rounded-lg transition-colors"
                aria-label="关闭侧边栏"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* Conversation List */}
          <div className="flex-1 overflow-y-auto scrollbar-elegant p-3">
            <p className="text-sm text-muted-foreground/60 text-center py-12 leading-relaxed">
              登录后查看历史对话记录
            </p>
          </div>

          {/* Footer - New Chat Button */}
          <div className="p-3 border-t border-border/40">
            <button
              onClick={() => {
                if (onNewConversation) onNewConversation();
              }}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-primary to-[hsl(220,38%,32%)] text-white rounded-xl hover:shadow-glow-primary transition-all active:scale-[0.98] font-medium text-sm"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              新建对话
            </button>
          </div>
        </>
      )}
    </div>
  );
}
