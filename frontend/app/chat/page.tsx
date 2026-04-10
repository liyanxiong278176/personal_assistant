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
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  const transportRef = useRef<ReturnType<typeof createChatTransport> | null>(null);
  const streamingMessageRef = useRef<string>("");
  const activeConversationRef = useRef<string | null>(null);
  const { isAuthenticated, user } = useAuthStore();
  const { setActiveConversation, createConversation, activeConversationId: storeActiveConversationId, clear: clearConversations, fetchConversations } = useConversationStore();

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

  // Clear all conversation data when user logs out
  useEffect(() => {
    if (!isAuthenticated) {
      // User logged out - clear all conversation data
      setMessages([]);
      setCurrentConversationId(null);
      activeConversationRef.current = null;  // Clear ref
      clearConversations();
      if (transportRef.current) {
        transportRef.current.setConversationId("");
      }
    }
  }, [isAuthenticated, clearConversations]);

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

  // Sync auth user ID to userManager and transport when user logs in
  useEffect(() => {
    if (isAuthenticated && user?.id) {
      // Sync user ID to userManager
      const currentUserId = userManager.getUserId();
      if (currentUserId !== user.id) {
        userManager.setUserId(user.id);
        console.log('[Chat] Synced auth user ID to userManager:', user.id);

        // Update transport with new user ID
        if (transportRef.current) {
          transportRef.current.setUserId(user.id);
          console.log('[Chat] Updated transport user ID:', user.id);
        }

        // Update local state
        setUserId(user.id);
      }

      // Fetch conversations on mount when user is authenticated
      // This ensures the sidebar shows all conversations after refresh
      fetchConversations().catch(err => {
        console.warn('[Chat] Failed to fetch conversations:', err);
      });
    }
  }, [isAuthenticated, user?.id]);

  // Initialize from store on mount (after user is loaded)
  // This handles page refresh by restoring the active conversation
  useEffect(() => {
    if (!isAuthenticated || !userId) return;  // Wait for user to be loaded

    // Only initialize if we don't have a local conversation ID
    if (!currentConversationId && storeActiveConversationId) {
      console.log('[Chat] Initializing from store:', storeActiveConversationId);
      setCurrentConversationId(storeActiveConversationId);
      activeConversationRef.current = storeActiveConversationId;
      loadConversationMessages(storeActiveConversationId);
      // Set transport conversation ID
      if (transportRef.current) {
        transportRef.current.setConversationId(storeActiveConversationId);
      }
    }
  }, [isAuthenticated, userId, currentConversationId, storeActiveConversationId]);

  // Load messages for active conversation from store (after refresh)
  useEffect(() => {
    if (storeActiveConversationId && storeActiveConversationId !== currentConversationId) {
      // Store has active conversation but local state doesn't match
      console.log('[Chat] Store conversation changed:', storeActiveConversationId);
      setCurrentConversationId(storeActiveConversationId);
      activeConversationRef.current = storeActiveConversationId;  // Update ref
      loadConversationMessages(storeActiveConversationId);
      // Update transport conversation ID
      if (transportRef.current) {
        transportRef.current.setConversationId(storeActiveConversationId);
      }
    }
  }, [storeActiveConversationId]);

  // Helper function to load conversation messages
  const loadConversationMessages = useCallback(async (conversationId: string) => {
    try {
      const history = await conversationsApi.getMessages(conversationId);
      setMessages(history);
    } catch (error) {
      console.error("Failed to load conversation messages:", error);
      setMessages([]);
    }
  }, []);  // Empty deps is fine - this only depends on the API which is stable

  // Handle sending message
  const handleSendMessage = useCallback(async () => {
    if ((!input.trim() && !selectedImage) || isLoading) return;

    const messageContent = input.trim();

    const userMessage: Message = {
      id: `user_${Date.now()}`,
      role: "user",
      content: messageContent,
      createdAt: new Date(),
    };

    // Add image data if present
    if (selectedImage) {
      (userMessage as any).image = {
        data: selectedImage,
      };
    }

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setSelectedImage(null);
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

      // Capture current conversation ID for use in callbacks
      const sendingConversationId = currentConversationId;

      await transport.sendMessage(messageContent, {
        imageData: selectedImage || undefined,
        onChunk: (chunk: string) => {
          // Only update if we're still on this conversation
          if (activeConversationRef.current !== sendingConversationId) {
            return;
          }
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
          // Only update if we're still on this conversation
          if (activeConversationRef.current !== sendingConversationId) {
            return;
          }
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
          // Only update conversation ID if we're still on this conversation
          if (activeConversationRef.current !== sendingConversationId) {
            return;
          }
          const convId = transport.getConversationId();
          // Always update conversation ID from transport
          if (convId) {
            setCurrentConversationId(convId);
            activeConversationRef.current = convId;
            // Also sync with store
            setActiveConversation(convId);
          }
        },
        onError: (error: string) => {
          clearTimeout(safetyTimeout);
          // Only update if we're still on this conversation
          if (activeConversationRef.current !== sendingConversationId) {
            setIsLoading(false);
            return;
          }
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
  }, [input, isLoading, currentConversationId, selectedImage]);

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
    console.log('[ChatPage] handleConversationSelect called:', { conversationId, currentConversationId, isLoading });

    // If currently generating and switching to a different conversation, stop the stream first
    if (isLoading && conversationId !== currentConversationId) {
      console.log('[ChatPage] Stopping current stream before switching');
      transportRef.current?.sendStop();
      // Wait a bit for the stop to take effect
      await new Promise(resolve => setTimeout(resolve, 100));
      setIsLoading(false);
    }

    // Handle empty string or null - clear messages (use empty session)
    if (!conversationId || conversationId === "") {
      console.log('[ChatPage] Clearing messages (empty session)');
      setCurrentConversationId(null);
      setActiveConversation(null);
      setMessages([]);
      if (transportRef.current) {
        transportRef.current.setConversationId("");
      }
      return;
    }

    // Don't switch if already on this conversation (unless stopping stream above)
    if (conversationId === currentConversationId && !isLoading) {
      console.log('[ChatPage] Already on this conversation, skipping');
      return;
    }

    // Clear current messages first before loading new ones
    setMessages([]);
    setCurrentConversationId(conversationId);
    setActiveConversation(conversationId);
    activeConversationRef.current = conversationId;  // Update ref immediately
    if (transportRef.current) {
      transportRef.current.setConversationId(conversationId);
    }

    console.log('[ChatPage] Loading messages for conversation:', conversationId);
    // Load conversation messages from backend
    try {
      const history = await conversationsApi.getMessages(conversationId);
      console.log('[ChatPage] Messages loaded:', history.length);
      setMessages(history);
    } catch (error) {
      console.error("[ChatPage] Failed to load conversation messages:", error);
      setMessages([]);
    }
  }, [setActiveConversation, isLoading, currentConversationId]);

  return (
    <div className="flex h-screen bg-background">
      <aside
        className={`
          ${sidebarOpen ? "w-64" : "w-0"}
          transition-all duration-300
          border-r border-border/40
          bg-card/30
          backdrop-blur-sm
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

      <main className="flex-1 flex flex-col relative">
        {/* Decorative ambient glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[200px] pointer-events-none">
          <div className="absolute inset-0 bg-gradient-radial opacity-30" />
        </div>

        <header className="relative z-10 h-14 border-b border-border/50 flex items-center justify-between px-4 gap-2 glass-card/30">
          <div className="flex items-center gap-3">
            <button
              onClick={toggleSidebar}
              className="lg:hidden p-2 hover:bg-muted/60 rounded-lg transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            {/* Logo */}
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-[hsl(25,65%,50%)] flex items-center justify-center shadow-soft">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                  <path d="M2 17l10 5 10-5"/>
                  <path d="M2 12l10 5 10-5"/>
                </svg>
              </div>
              <h1 className="font-display text-xl font-semibold text-gradient-warm hidden sm:block">
                AI Travel Assistant
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {isAuthenticated && user ? (
              <div className="flex items-center gap-2 mr-1">
                {/* 评估体系按钮 */}
                <a
                  href="/eval"
                  className="px-3 py-1.5 text-xs font-medium rounded-lg flex items-center gap-1.5
                    bg-gradient-to-r from-primary/10 to-accent/10 border border-border/50
                    hover:from-primary/20 hover:to-accent/20
                    text-primary hover:text-primary
                    transition-all"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  评估体系
                </a>
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.username || user.email}
                    className="w-7 h-7 rounded-full object-cover ring-2 ring-white/50"
                  />
                ) : (
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-sm">
                    <span className="text-[11px] font-semibold text-white">
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
              className="p-2 hover:bg-muted/60 rounded-lg flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-all"
            >
              {isAuthenticated ? (
                <>
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                  </svg>
                  <span className="hidden sm:inline text-xs">账号</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
                    <polyline points="10 17 15 12 10 7"/>
                    <line x1="15" y1="12" x2="3" y2="12"/>
                  </svg>
                  <span className="hidden sm:inline text-xs">登录</span>
                </>
              )}
            </button>
            <a
              href="/settings"
              className="p-2 hover:bg-muted/60 rounded-lg flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-all"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
              <span className="hidden sm:inline text-xs">设置</span>
            </a>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto scrollbar-elegant">
          <MessageList messages={messages} />
        </div>

        <div className="relative z-10 border-t border-border/50 bg-background/80 backdrop-blur-md">
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={handleSendMessage}
            onStop={handleStop}
            isLoading={isLoading}
            onImageChange={setSelectedImage}
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
