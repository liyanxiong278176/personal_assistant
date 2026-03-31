"use client";

import { useState, useRef, useEffect } from "react";
import { format, isToday, isYesterday, parseISO } from "date-fns";
import { zhCN } from "date-fns/locale";
import { Pin, PinOff, Trash2, Archive, Check, X } from "lucide-react";
import type { Conversation } from "@/lib/types";

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onClick: () => void;
  onRename: (id: string, newTitle: string) => Promise<void>;
  onTogglePin: (id: string, isPinned: boolean) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onArchive?: (id: string) => Promise<void>;
}

export function ConversationItem({
  conversation,
  isActive,
  onClick,
  onRename,
  onTogglePin,
  onDelete,
  onArchive,
}: ConversationItemProps) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(conversation.title);
  const [isContextMenuOpen, setIsContextMenuOpen] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const itemRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isRenaming && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isRenaming]);

  useEffect(() => {
    setRenameValue(conversation.title);
  }, [conversation.title]);

  // Close context menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (itemRef.current && !itemRef.current.contains(e.target as Node)) {
        setIsContextMenuOpen(false);
      }
    };

    if (isContextMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isContextMenuOpen]);

  const handleDoubleClick = () => {
    setIsRenaming(true);
  };

  const handleRenameSubmit = async () => {
    if (renameValue.trim() && renameValue !== conversation.title) {
      setIsPending(true);
      try {
        await onRename(conversation.id, renameValue.trim());
        setIsRenaming(false);
      } catch (error) {
        console.error("Failed to rename:", error);
        setRenameValue(conversation.title);
      } finally {
        setIsPending(false);
      }
    } else {
      setIsRenaming(false);
      setRenameValue(conversation.title);
    }
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleRenameSubmit();
    } else if (e.key === "Escape") {
      setIsRenaming(false);
      setRenameValue(conversation.title);
    }
  };

  const formatTime = (dateString: string) => {
    const date = parseISO(dateString);
    if (isToday(date)) {
      return format(date, "HH:mm");
    }
    if (isYesterday(date)) {
      return "昨天";
    }
    return format(date, "M月d日", { locale: zhCN });
  };

  const handleTogglePin = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsPending(true);
    try {
      await onTogglePin(conversation.id, !conversation.is_pinned);
    } finally {
      setIsPending(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsPending(true);
    try {
      await onDelete(conversation.id);
    } finally {
      setIsPending(false);
    }
  };

  const handleArchive = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onArchive) {
      setIsPending(true);
      try {
        await onArchive(conversation.id);
      } finally {
        setIsPending(false);
      }
    }
  };

  return (
    <div ref={itemRef} className="relative group">
      <div
        className={`
          flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer
          transition-colors relative
          ${isActive ? "bg-accent text-accent-foreground" : "hover:bg-muted/50"}
          ${isPending ? "opacity-50 pointer-events-none" : ""}
        `}
        onClick={onClick}
        onDoubleClick={handleDoubleClick}
      >
        {/* Pin icon for pinned conversations */}
        {conversation.is_pinned && (
          <Pin className="w-3 h-3 text-muted-foreground flex-shrink-0" />
        )}

        {/* Title or rename input */}
        {isRenaming ? (
          <input
            ref={inputRef}
            type="text"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={handleRenameSubmit}
            onKeyDown={handleRenameKeyDown}
            className="flex-1 bg-background border border-input rounded px-2 py-0.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="flex-1 truncate text-sm">{conversation.title}</span>
        )}

        {/* Time */}
        <span className="text-xs text-muted-foreground flex-shrink-0">
          {formatTime(conversation.updated_at)}
        </span>

        {/* Context menu button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            setIsContextMenuOpen(!isContextMenuOpen);
          }}
          className="opacity-0 group-hover:opacity-100 p-1 hover:bg-muted rounded transition-opacity"
          aria-label="更多选项"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
          </svg>
        </button>
      </div>

      {/* Context menu dropdown */}
      {isContextMenuOpen && (
        <div className="absolute right-0 top-full mt-1 z-50 min-w-[160px] bg-popover border border-border rounded-md shadow-md">
          <div className="py-1">
            <button
              onClick={handleTogglePin}
              className="w-full px-3 py-2 text-left text-sm hover:bg-muted flex items-center gap-2 transition-colors"
            >
              {conversation.is_pinned ? (
                <>
                  <PinOff className="w-4 h-4" />
                  取消置顶
                </>
              ) : (
                <>
                  <Pin className="w-4 h-4" />
                  置顶
                </>
              )}
            </button>
            {onArchive && (
              <button
                onClick={handleArchive}
                className="w-full px-3 py-2 text-left text-sm hover:bg-muted flex items-center gap-2 transition-colors"
              >
                <Archive className="w-4 h-4" />
                归档
              </button>
            )}
            <button
              onClick={() => {
                setIsContextMenuOpen(false);
                setIsRenaming(true);
              }}
              className="w-full px-3 py-2 text-left text-sm hover:bg-muted flex items-center gap-2 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
              </svg>
              重命名
            </button>
            <button
              onClick={handleDelete}
              className="w-full px-3 py-2 text-left text-sm hover:bg-destructive/10 text-destructive flex items-center gap-2 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              删除
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
