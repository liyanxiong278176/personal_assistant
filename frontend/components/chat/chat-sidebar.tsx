"use client";

import { ConversationList } from "@/components/conversations/conversation-list";
import { useAuthStore } from "@/lib/store/auth-store";

interface ChatSidebarProps {
  onClose?: () => void;
  onConversationSelect?: (id: string) => void;
  onNewConversation?: () => void;
}

export function ChatSidebar({ onClose, onConversationSelect, onNewConversation }: ChatSidebarProps) {
  const { isAuthenticated } = useAuthStore();

  return (
    <div className="h-full flex flex-col">
      {isAuthenticated ? (
        <ConversationList
          onNewConversation={onNewConversation}
          onConversationSelect={onConversationSelect}
        />
      ) : (
        <>
          {/* Header */}
          <div className="h-14 border-b border-border flex items-center justify-between px-4">
            <h2 className="font-semibold text-sm text-foreground/80">聊天历史</h2>
            {onClose && (
              <button
                onClick={onClose}
                className="p-1 hover:bg-muted rounded"
                aria-label="Close sidebar"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* Conversation List */}
          <div className="flex-1 overflow-y-auto p-2">
            <p className="text-sm text-muted-foreground text-center py-8">
              请先登录以查看历史对话
            </p>
          </div>

          {/* Footer - New Chat Button */}
          <div className="p-2 border-t border-border">
            <button
              onClick={onNewConversation}
              className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition text-sm font-medium"
            >
              新建对话
            </button>
          </div>
        </>
      )}
    </div>
  );
}
