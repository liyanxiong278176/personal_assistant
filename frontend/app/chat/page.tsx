"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { ChatSidebar } from "@/components/chat/chat-sidebar";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageList } from "@/components/chat/message-list";
import { AuthModal } from "@/components/auth/auth-modal";
import { createChatTransport } from "@/lib/chat-transport";
import { userManager } from "@/lib/user-manager";
import { useAuthStore } from "@/lib/store/auth-store";
import { useConversationStore } from "@/lib/store/conversation-store";
import { conversationsApi } from "@/lib/api/conversations";
import type { Message, Itinerary } from "@/lib/types";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);

  const transportRef = useRef<ReturnType<typeof createChatTransport> | null>(null);
  const streamingMessageRef = useRef<string>("");
  const { isAuthenticated, user } = useAuthStore();
  const { setActiveConversation, createConversation } = useConversationStore();

  // Initialize user manager on mount
  useEffect(() => {
    async function initUser() {
      try {
        const id = await userManager.initialize();
        setUserId(id);
        console.log('[Chat] User initialized:', id);
      } catch (error) {
        console.error('[Chat] Failed to initialize user:', error);
      }
    }
    initUser();
  }, []);

  // Initialize transport on mount
  useEffect(() => {
    const transport = createChatTransport();
    transportRef.current = transport;

    return () => {
      transport.disconnect();
    };
  }, []);

  // Set userId to transport when userId becomes available
  useEffect(() => {
    if (userId && transportRef.current) {
      transportRef.current.setUserId(userId);
      console.log('[Chat] User ID set to transport:', userId);
    }
  }, [userId]);

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

  // Handle new conversation creation
  const handleNewConversation = useCallback(async () => {
    if (!isAuthenticated) {
      // For non-authenticated users, just clear messages
      setMessages([]);
      setCurrentConversationId(null);
      if (transportRef.current) {
        transportRef.current.setConversationId("");
      }
      return;
    }

    try {
      const newConv = await createConversation();
      setCurrentConversationId(newConv.id);
      setActiveConversation(newConv.id);
      setMessages([]);
      if (transportRef.current) {
        transportRef.current.setConversationId(newConv.id);
      }
    } catch (error) {
      console.error("Failed to create conversation:", error);
    }
  }, [isAuthenticated, createConversation, setActiveConversation]);

  // Handle conversation selection
  const handleConversationSelect = useCallback(async (conversationId: string) => {
    setCurrentConversationId(conversationId);
    setActiveConversation(conversationId);
    if (transportRef.current) {
      transportRef.current.setConversationId(conversationId);
    }

    // Load conversation messages from backend
    try {
      const history = await conversationsApi.getMessages(conversationId);
      setMessages(history);
    } catch (error) {
      console.error("Failed to load conversation messages:", error);
      setMessages([]);
    }
  }, [setActiveConversation]);

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
        <ChatSidebar
          onClose={() => setSidebarOpen(false)}
          onNewConversation={handleNewConversation}
          onConversationSelect={handleConversationSelect}
        />
      </aside>

      <main className="flex-1 flex flex-col">
        <header className="h-14 border-b border-border flex items-center justify-between px-4 gap-2">
          <div className="flex items-center gap-2">
            <button
              onClick={toggleSidebar}
              className="lg:hidden p-2 hover:bg-muted rounded"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <h1 className="font-semibold text-lg">AI Travel Assistant</h1>
          </div>
          <div className="flex items-center gap-2">
            {isAuthenticated && user ? (
              <div className="flex items-center gap-2">
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.username || user.email}
                    className="w-7 h-7 rounded-full object-cover"
                  />
                ) : (
                  <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center">
                    <span className="text-xs font-medium text-primary">
                      {(user.username || user.email)?.[0]?.toUpperCase() || "U"}
                    </span>
                  </div>
                )}
                <span className="text-sm text-muted-foreground hidden sm:inline">
                  {user.username || user.email.split("@")[0]}
                </span>
              </div>
            ) : null}
            <button
              onClick={() => setShowAuthModal(true)}
              className="p-2 hover:bg-muted rounded flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <span className="hidden sm:inline">{isAuthenticated ? "账号" : "登录"}</span>
            </button>
            <a
              href="/settings"
              className="p-2 hover:bg-muted rounded flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span className="hidden sm:inline">设置</span>
            </a>
          </div>
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

      {/* Auth Modal */}
      {showAuthModal && (
        <AuthModal isOpen={showAuthModal} onClose={() => setShowAuthModal(false)} />
      )}
    </div>
  );
}
