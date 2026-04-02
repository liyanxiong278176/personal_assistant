"use client";

import { useRef } from "react";
import { SendHorizonal, Square, Mic, Sparkles } from "lucide-react";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop?: () => void;
  isLoading?: boolean;
}

export function ChatInput({ value, onChange, onSend, onStop, isLoading }: ChatInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSend();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const canSend = value.trim().length > 0 && !isLoading;

  return (
    <div className="p-4">
      <div className="max-w-4xl mx-auto">
        {/* Input Container */}
        <form onSubmit={handleSubmit} className="relative">
          <div className="relative flex items-end gap-3 p-2 bg-card/90 border border-border/60 rounded-2xl shadow-soft-lg backdrop-blur-md transition-all focus-within:border-ring/40 focus-within:shadow-glow-primary">
            {/* Input */}
            <div className="flex-1 flex items-center">
              <input
                ref={inputRef}
                type="text"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="告诉我想去哪里旅行..."
                disabled={isLoading}
                className="w-full px-3 py-2.5 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50 disabled:opacity-50"
                autoComplete="off"
              />
            </div>

            {/* Divider */}
            <div className="w-px h-8 bg-border/50 self-center flex-shrink-0" />

            {/* Action Buttons */}
            <div className="flex items-center gap-1 pr-1 flex-shrink-0">
              {isLoading && onStop ? (
                <button
                  type="button"
                  onClick={onStop}
                  className="w-9 h-9 rounded-xl bg-destructive/10 hover:bg-destructive/20 text-destructive flex items-center justify-center transition-all active:scale-95"
                  title="停止生成"
                >
                  <Square className="w-3.5 h-3.5 fill-current" />
                </button>
              ) : (
                <>
                  {/* Send Button */}
                  <button
                    type="submit"
                    disabled={!canSend}
                    className={`
                      w-9 h-9 rounded-xl flex items-center justify-center transition-all active:scale-95
                      ${canSend
                        ? "bg-gradient-to-br from-primary to-[hsl(220,38%,32%)] text-white shadow-glow-primary hover:shadow-glow"
                        : "bg-muted/50 text-muted-foreground/40 cursor-not-allowed"
                      }
                    `}
                    title="发送"
                  >
                    <SendHorizonal className={`w-4 h-4 ${canSend ? "" : ""}`} />
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Quick suggestions hint */}
          <div className="flex items-center justify-center gap-2 mt-2.5">
            <Sparkles className="w-3 h-3 text-muted-foreground/40" />
            <span className="text-[11px] text-muted-foreground/50">
              按 Enter 发送，Shift + Enter 换行
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}
