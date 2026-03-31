"use client";

import { useState } from "react";
import { ChatSidebar } from "@/components/chat/chat-sidebar";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageList } from "@/components/chat/message-list";
import type { Message } from "@/lib/types";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [input, setInput] = useState("");

  const handleSendMessage = () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
      createdAt: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");

    // TODO: Connect to backend in Plan 04
  };

  const toggleSidebar = () => {
    setSidebarOpen((prev) => !prev);
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar - per D-04 and D-05 */}
      <aside
        className={`
          ${sidebarOpen ? "w-64" : "w-0"}
          transition-all duration-300
          border-r border-border
          bg-muted/50
          overflow-hidden
          lg:block
          hidden
        `}
      >
        <ChatSidebar onClose={() => setSidebarOpen(false)} />
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col">
        {/* Header */}
        <header className="h-14 border-b border-border flex items-center px-4 gap-2">
          <button
            onClick={toggleSidebar}
            className="lg:hidden p-2 hover:bg-muted rounded"
            aria-label="Toggle sidebar"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <h1 className="font-semibold text-lg">AI Travel Assistant</h1>
        </header>

        {/* Messages Area - per D-04 ChatGPT style */}
        <div className="flex-1 overflow-y-auto">
          <MessageList messages={messages} />
        </div>

        {/* Input Area - fixed at bottom per D-04 */}
        <div className="border-t border-border bg-background">
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={handleSendMessage}
          />
        </div>
      </main>
    </div>
  );
}
