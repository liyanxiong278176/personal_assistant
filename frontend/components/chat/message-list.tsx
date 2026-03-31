"use client";

import type { Message } from "@/lib/types";
import { ChatItinerary } from "./chat-itinerary";

interface MessageListProps {
  messages: Message[];
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="max-w-4xl mx-auto py-4 px-4">
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full min-h-[400px]">
          <div className="text-center">
            <h2 className="text-2xl font-semibold mb-2">AI Travel Assistant</h2>
            <p className="text-muted-foreground">
              你的智能旅行规划助手，随时为你提供旅行建议
            </p>
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
                {/* Message bubble */}
                {message.content && (
                  <div
                    className={`
                      rounded-lg px-4 py-3
                      ${
                        message.role === "user"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-foreground"
                      }
                    `}
                  >
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
