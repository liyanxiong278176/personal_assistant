"use client";

import { useRef, useState } from "react";
import { SendHorizonal, Square, Image as ImageIcon, X } from "lucide-react";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop?: () => void;
  isLoading?: boolean;
  onImageChange?: (imageData: string | null) => void;
}

export function ChatInput({ value, onChange, onSend, onStop, isLoading, onImageChange }: ChatInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSend();
    // Clear image after sending
    if (previewImage) {
      setPreviewImage(null);
      onImageChange?.(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith("image/")) {
      alert("请选择图片文件");
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      alert("图片大小不能超过5MB");
      return;
    }

    // Convert to base64
    const reader = new FileReader();
    reader.onload = (event) => {
      const base64 = event.target?.result as string;
      // Remove data:image/xxx;base64, prefix
      const base64Data = base64.split(",")[1];
      setPreviewImage(base64);
      onImageChange?.(base64Data);
    };
    reader.readAsDataURL(file);

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleRemoveImage = () => {
    setPreviewImage(null);
    onImageChange?.(null);
  };

  const canSend = (value.trim().length > 0 || previewImage) && !isLoading;

  return (
    <div className="p-4">
      <div className="max-w-4xl mx-auto">
        {/* Image Preview */}
        {previewImage && (
          <div className="mb-2 max-w-4xl mx-auto">
            <div className="relative inline-flex items-center gap-2 p-2 bg-card/90 border border-border/60 rounded-xl">
              <div className="relative w-16 h-16 rounded-lg overflow-hidden bg-muted">
                <img
                  src={`data:image/jpeg;base64,${previewImage}`}
                  alt="Preview"
                  className="w-full h-full object-cover"
                />
              </div>
              <span className="text-xs text-muted-foreground">已选择图片</span>
              <button
                type="button"
                onClick={handleRemoveImage}
                className="p-1 hover:bg-destructive/10 rounded-md text-muted-foreground hover:text-destructive transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Input Container */}
        <form onSubmit={handleSubmit} className="relative">
          <div className="relative flex items-end gap-3 p-2 bg-card/90 border border-border/60 rounded-2xl shadow-soft-lg backdrop-blur-md transition-all focus-within:border-ring/40 focus-within:shadow-glow-primary">
            {/* Image Upload Button */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleImageSelect}
              className="hidden"
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
              className={`
                p-2 rounded-xl transition-all active:scale-95 flex-shrink-0
                ${isLoading
                  ? "text-muted-foreground/40 cursor-not-allowed"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }
              `}
              title="上传图片"
            >
              <ImageIcon className="w-5 h-5" />
            </button>

            {/* Input */}
            <div className="flex-1 flex items-center">
              <input
                ref={inputRef}
                type="text"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="告诉我想去哪里旅行... (可上传图片)"
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
            <span className="text-[11px] text-muted-foreground/50">
              按 Enter 发送，Shift + Enter 换行 · 支持上传图片识别景点
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}
