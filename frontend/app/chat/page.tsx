"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { ChatSidebar } from "@/components/chat/chat-sidebar";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageList } from "@/components/chat/message-list";
import { createChatTransport } from "@/lib/chat-transport";
import type { Message, Itinerary } from "@/lib/types";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);

  const transportRef = useRef<ReturnType<typeof createChatTransport> | null>(null);
  const streamingMessageRef = useRef<string>("");

  // Initialize transport on mount
  useEffect(() => {
    const transport = createChatTransport();
    transportRef.current = transport;

    return () => {
      transport.disconnect();
    };
  }, []);

  // Handle sending message
  const handleSendMessage = useCallback(async () => {
    if (!input.trim() || isLoading) return;

    const messageContent = input.trim();

    const userMessage: Message = {
      id: `user_${Date.now()}`,
      role: "user",
      content: messageContent,
      createdAt: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    streamingMessageRef.current = "";

    const assistantMessageId = `assistant_${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        createdAt: new Date(),
      },
    ]);

    // Safety timeout - always reset isLoading after 60 seconds
    const safetyTimeout = setTimeout(() => {
      console.warn("[Chat] Safety timeout triggered, resetting isLoading");
      setIsLoading(false);
    }, 60000);

    try {
      const transport = transportRef.current;
      if (!transport) throw new Error("Transport not initialized");

      await transport.sendMessage(messageContent, {
        onChunk: (chunk: string) => {
          streamingMessageRef.current += chunk;
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: streamingMessageRef.current }
                : msg
            )
          );
        },
        onItinerary: (itinerary: Itinerary) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, itinerary }
                : msg
            )
          );
        },
        onDone: (messageId: string) => {
          clearTimeout(safetyTimeout);
          setIsLoading(false);
          const convId = transport.getConversationId();
          if (convId && !currentConversationId) {
            setCurrentConversationId(convId);
          }
        },
        onError: (error: string) => {
          clearTimeout(safetyTimeout);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: `Error: ${error}` }
                : msg
            )
          );
          setIsLoading(false);
        },
      });
    } catch (error) {
      clearTimeout(safetyTimeout);
      setMessages((prev) => prev.filter((msg) => msg.id !== assistantMessageId));
      setIsLoading(false);
    }
  }, [input, isLoading, currentConversationId]);

  const handleStop = useCallback(() => {
    transportRef.current?.sendStop();
  }, []);

  const toggleSidebar = () => {
    setSidebarOpen((prev) => !prev);
  };

  return (
    <div className="flex h-screen bg-background">
      <aside
        className={`
          ${sidebarOpen ? "w-64" : "w-0"}
          transition-all duration-300
          border-r border-border
          bg-muted/50
          overflow-hidden
          lg:block hidden
        `}
      >
        <ChatSidebar onClose={() => setSidebarOpen(false)} />
      </aside>

      <main className="flex-1 flex flex-col">
        <header className="h-14 border-b border-border flex items-center px-4 gap-2">
          <button
            onClick={toggleSidebar}
            className="lg:hidden p-2 hover:bg-muted rounded"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <h1 className="font-semibold text-lg">AI Travel Assistant</h1>
        </header>

        <div className="flex-1 overflow-y-auto">
          <MessageList messages={messages} />
        </div>

        <div className="border-t border-border bg-background">
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={handleSendMessage}
            onStop={handleStop}
            isLoading={isLoading}
          />
        </div>
      </main>
    </div>
  );
}
