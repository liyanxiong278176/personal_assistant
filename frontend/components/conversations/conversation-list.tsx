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

  // Load conversations on mount
  useEffect(() => {
    fetchConversations();
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
      if (conversation.is_pinned) {
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
      onNewConversation?.();
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
    await deleteConversation(id);
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
