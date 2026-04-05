"use client";

import type { Message } from "@/lib/types";
import { ChatItinerary } from "./chat-itinerary";
import { MapPin, Compass, Sparkles, Star } from "lucide-react";

interface MessageListProps {
  messages: Message[];
}

const SUGGESTIONS = [
  { icon: <MapPin className="w-4 h-4" />, text: "帮我规划一个北京3日游行程" },
  { icon: <Compass className="w-4 h-4" />, text: "推荐一些适合亲子旅行的目的地" },
  { icon: <Star className="w-4 h-4" />, text: "我想去日本赏樱，有什么建议？" },
  { icon: <Compass className="w-4 h-4" />, text: "周末从上海出发，适合2天的小众旅行" },
];

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="max-w-4xl mx-auto py-6 px-4">
      {messages.length === 0 ? (
        <div className="flex flex-col items-center justify-center min-h-[calc(100vh-220px)]">
          {/* Hero Section */}
          <div className="text-center max-w-xl">
            {/* Decorative Globe Icon */}
            <div className="relative inline-flex items-center justify-center mb-8">
              <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-accent/10 rounded-full blur-2xl scale-150" />
              <div className="relative w-20 h-20 rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-glow">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M2 12h20"/>
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                </svg>
              </div>
            </div>

            {/* Title */}
            <h2 className="font-display text-4xl font-bold text-gradient-display mb-3">
              开启你的旅行冒险
            </h2>
            <p className="text-muted-foreground text-base leading-relaxed mb-10">
              无论你想探索未知的目的地，还是优化下一次行程，<br className="hidden sm:block" />
              我都能为你量身定制完美的旅行计划
            </p>

            {/* Feature Pills */}
            <div className="flex flex-wrap justify-center gap-3 mb-12">
              {[
                "智能行程规划",
                "实时景点推荐",
                "预算优化建议",
                "图片识别景点",
              ].map((feature) => (
                <div
                  key={feature}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-card/80 border border-border/50 text-sm text-muted-foreground backdrop-blur-sm"
                >
                  <Sparkles className="w-3.5 h-3.5 text-accent" />
                  {feature}
                </div>
              ))}
            </div>

            {/* Suggestion Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {SUGGESTIONS.map((suggestion, idx) => (
                <div
                  key={idx}
                  className="group card-journal p-4 text-left cursor-pointer hover:border-accent/30 hover:shadow-ember"
                  onClick={() => {
                    const event = new CustomEvent('suggestion-click', { detail: suggestion.text });
                    window.dispatchEvent(event);
                  }}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center text-primary group-hover:from-primary/20 group-hover:to-accent/20 group-hover:scale-110 transition-all">
                      {suggestion.icon}
                    </div>
                    <span className="text-sm text-foreground/80 group-hover:text-foreground transition-colors leading-snug">
                      {suggestion.text}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${
                message.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div className={message.role === "user" ? "max-w-[80%]" : "max-w-full"}>
                {/* Image display for user messages */}
                {message.image && (
                  <div className="mb-2 rounded-lg overflow-hidden border border-border/50">
                    <img
                      src={`data:image/jpeg;base64,${message.image.data}`}
                      alt="Uploaded"
                      className="max-w-full h-auto max-h-64 object-cover"
                    />
                  </div>
                )}

                {/* Message bubble */}
                {message.content && (
                  <div
                    className={`
                      rounded-lg px-4 py-3
                      ${
                        message.role === "user"
                          ? "message-user"
                          : "message-assistant"
                      }
                    `}
                  >
                    {message.role === "assistant" && (
                      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-border/30">
                        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                            <path d="M2 17l10 5 10-5"/>
                            <path d="M2 12l10 5 10-5"/>
                          </svg>
                        </div>
                        <span className="text-xs font-medium text-muted-foreground">AI 助手</span>
                      </div>
                    )}
                    <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  </div>
                )}

                {/* Itinerary display for assistant */}
                {message.role === "assistant" && message.itinerary && (
                  <ChatItinerary itinerary={message.itinerary} />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
