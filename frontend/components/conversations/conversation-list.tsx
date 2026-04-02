"use client";

import { useEffect, useMemo } from "react";
import { format, isToday, isYesterday, subDays, parseISO, startOfDay } from "date-fns";
import { zhCN } from "date-fns/locale";
import { Plus, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConversationSearch } from "./conversation-search";
import { ConversationItem } from "./conversation-item";
import { useConversationStore } from "@/lib/store/conversation-store";
import type { Conversation } from "@/lib/types";

interface ConversationListProps {
  onNewConversation?: () => void;
  onConversationSelect?: (id: string) => void;
}

interface GroupedConversations {
  pinned: Conversation[];
  today: Conversation[];
  yesterday: Conversation[];
  earlier: Conversation[];
}

export function ConversationList({
  onNewConversation,
  onConversationSelect,
}: ConversationListProps) {
  const {
    conversations,
    activeConversationId,
    isLoading,
    searchQuery,
    setSearchQuery,
    createConversation,
    updateConversation,
    togglePin,
    deleteConversation,
    fetchConversations,
  } = useConversationStore();

  // Load conversations on mount and when auth state changes
  useEffect(() => {
    // Delay fetch to ensure auth headers are ready
    const timer = setTimeout(() => {
      fetchConversations();
    }, 100);
    return () => clearTimeout(timer);
  }, [fetchConversations]);

  // Group conversations by time
  const groupedConversations = useMemo(() => {
    const groups: GroupedConversations = {
      pinned: [],
      today: [],
      yesterday: [],
      earlier: [],
    };

    const sortedConversations = [...conversations].sort((a, b) =>
      new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );

    for (const conversation of sortedConversations) {
      if (conversation.pinned) {
        groups.pinned.push(conversation);
        continue;
      }

      const date = parseISO(conversation.updated_at);
      if (isToday(date)) {
        groups.today.push(conversation);
      } else if (isYesterday(date)) {
        groups.yesterday.push(conversation);
      } else {
        groups.earlier.push(conversation);
      }
    }

    return groups;
  }, [conversations]);

  // Group earlier conversations by date
  const earlierGroupedByDate = useMemo(() => {
    const groups: Record<string, Conversation[]> = {};
    const todayStart = startOfDay(new Date());
    const yesterdayStart = subDays(todayStart, 1);

    for (const conversation of groupedConversations.earlier) {
      const date = parseISO(conversation.updated_at);
      const dateKey = format(date, "yyyy年M月d日", { locale: zhCN });

      if (!groups[dateKey]) {
        groups[dateKey] = [];
      }
      groups[dateKey].push(conversation);
    }

    return groups;
  }, [groupedConversations.earlier]);

  const handleNewConversation = async () => {
    try {
      const newConv = await createConversation();
      onConversationSelect?.(newConv.id);
      // Don't call onNewConversation callback - it causes duplicate creation
      // Parent should handle clearing messages if needed
    } catch (error) {
      console.error("Failed to create conversation:", error);
    }
  };

  const handleRename = async (id: string, newTitle: string) => {
    await updateConversation(id, { title: newTitle });
  };

  const handleTogglePin = async (id: string, isPinned: boolean) => {
    await togglePin(id, isPinned);
  };

  const handleDelete = async (id: string) => {
    console.log('[ConversationList] handleDelete called:', { id, activeConversationId, conversationsCount: conversations.length });

    // If deleting the active conversation, find the next one to switch to
    if (id === activeConversationId) {
      // Sort conversations by updated_at (most recent first)
      const sortedConversations = [...conversations].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      );
      console.log('[ConversationList] Sorted conversations:', sortedConversations.map(c => c.id));

      // Find the index of the conversation being deleted
      const currentIndex = sortedConversations.findIndex(c => c.id === id);
      console.log('[ConversationList] Current index:', currentIndex);

      // Find the next conversation to switch to (either the one after or the one before)
      let nextConversation: Conversation | null = null;

      if (sortedConversations.length > 1) {
        // Try to get the next one in the list (if deleted is not the last)
        if (currentIndex < sortedConversations.length - 1) {
          nextConversation = sortedConversations[currentIndex + 1];
        } else if (currentIndex > 0) {
          // If deleted was the last, use the one before
          nextConversation = sortedConversations[currentIndex - 1];
        }
      }
      console.log('[ConversationList] Next conversation:', nextConversation?.id || 'none');

      // Delete the conversation first
      await deleteConversation(id);
      console.log('[ConversationList] Conversation deleted');

      // If we found a next conversation, switch to it
      if (nextConversation) {
        console.log('[ConversationList] Switching to next conversation:', nextConversation.id);
        // Use the onConversationSelect callback to switch to the next conversation
        onConversationSelect?.(nextConversation.id);
      } else {
        console.log('[ConversationList] No next conversation, clearing messages');
        // No other conversation, clear messages (use empty session)
        // The parent component should handle clearing messages
        onConversationSelect?.("");
      }
    } else {
      console.log('[ConversationList] Not active conversation, just deleting');
      // Not deleting active conversation, just delete
      await deleteConversation(id);
    }
  };

  const handleSelect = (id: string) => {
    onConversationSelect?.(id);
  };

  const renderGroup = (title: string, conversations: Conversation[]) => {
    if (conversations.length === 0) return null;

    return (
      <div key={title} className="mb-4">
        <h3 className="px-3 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {title}
        </h3>
        <div className="space-y-0.5">
          {conversations.map((conversation) => (
            <ConversationItem
              key={conversation.id}
              conversation={conversation}
              isActive={conversation.id === activeConversationId}
              onClick={() => handleSelect(conversation.id)}
              onRename={handleRename}
              onTogglePin={handleTogglePin}
              onDelete={handleDelete}
            />
          ))}
        </div>
      </div>
    );
  };

  const renderEarlierGroups = () => {
    const dates = Object.keys(earlierGroupedByDate).sort(
      (a, b) => new Date(b).getTime() - new Date(a).getTime()
    );

    return dates.map((dateKey) => renderGroup(dateKey, earlierGroupedByDate[dateKey]));
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="h-14 border-b border-border flex flex-col px-3 py-2 gap-2">
        <h2 className="font-semibold text-sm text-foreground/80">对话列表</h2>
        <ConversationSearch
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="搜索对话..."
        />
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading && conversations.length === 0 ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="w-5 h-5 text-muted-foreground animate-spin" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-sm text-muted-foreground">
              {searchQuery ? "没有找到匹配的对话" : "暂无对话"}
            </p>
            {!searchQuery && (
              <Button
                variant="ghost"
                onClick={handleNewConversation}
                className="mt-2 h-8 px-3 text-sm"
              >
                开始新对话
              </Button>
            )}
          </div>
        ) : (
          <>
            {renderGroup("置顶", groupedConversations.pinned)}
            {renderGroup("今天", groupedConversations.today)}
            {renderGroup("昨天", groupedConversations.yesterday)}
            {renderEarlierGroups()}
          </>
        )}
      </div>

      {/* Footer - New Chat Button */}
      <div className="p-2 border-t border-border">
        <Button
          onClick={handleNewConversation}
          className="w-full h-9 px-4 text-sm"
        >
          <Plus className="w-4 h-4 mr-2" />
          新建对话
        </Button>
      </div>
    </div>
  );
}
