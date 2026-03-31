"use client";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop?: () => void;
  isLoading?: boolean;
}

export function ChatInput({ value, onChange, onSend, onStop, isLoading }: ChatInputProps) {
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

  return (
    <form onSubmit={handleSubmit} className="p-4">
      <div className="max-w-4xl mx-auto flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的旅行问题..."
          disabled={isLoading}
          className="flex-1 px-4 py-3 bg-muted border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
        {isLoading && onStop ? (
          <button
            type="button"
            onClick={onStop}
            className="px-6 py-3 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition font-medium"
          >
            停止
          </button>
        ) : (
          <button
            type="submit"
            disabled={!value.trim() || isLoading}
            className="px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition font-medium"
          >
            发送
          </button>
        )}
      </div>
    </form>
  );
}
