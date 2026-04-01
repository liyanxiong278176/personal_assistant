import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  Conversation,
  ConversationTag,
  ConversationListResponse,
  ConversationUpdate,
  CreateConversationRequest,
  UpdateConversationRequest,
  SearchConversationsParams,
  CreateTagRequest,
} from "../types";

interface ConversationStore {
  conversations: Conversation[];
  activeConversationId: string | null;
  tags: ConversationTag[];
  isLoading: boolean;
  error: string | null;
  searchQuery: string;
  selectedTags: string[];
  showPinnedOnly: boolean;
  page: number;
  pageSize: number;
  total: number;
  hasMore: boolean;

  setActiveConversation: (id: string | null) => void;
  fetchConversations: (params?: SearchConversationsParams) => Promise<void>;
  createConversation: (data?: CreateConversationRequest) => Promise<Conversation>;
  updateConversation: (id: string, data: UpdateConversationRequest) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  togglePin: (id: string, isPinned: boolean) => Promise<void>;
  addTag: (conversationId: string, tagName: string) => Promise<void>;
  removeTag: (conversationId: string, tagName: string) => Promise<void>;
  fetchTags: () => Promise<void>;
  createTag: (data: CreateTagRequest) => Promise<ConversationTag>;
  deleteTag: (tagId: string) => Promise<void>;
  setSearchQuery: (query: string) => void;
  setSelectedTags: (tags: string[]) => void;
  setShowPinnedOnly: (show: boolean) => void;
  resetFilters: () => void;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
  clear: () => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Helper function to get auth headers
const getAuthHeaders = (): HeadersInit => {
  if (typeof window === "undefined") return {};

  try {
    const stored = localStorage.getItem("auth-storage");
    if (!stored) return {};

    const parsed = JSON.parse(stored);
    const token = parsed.state?.token;

    if (!token) return {};

    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    };
  } catch {
    return { "Content-Type": "application/json" };
  }
};

export const useConversationStore = create<ConversationStore>()(
  persist(
    (set, get) => ({
  conversations: [],
  activeConversationId: null,
  tags: [],
  isLoading: false,
  error: null,
  searchQuery: "",
  selectedTags: [],
  showPinnedOnly: false,
  page: 1,
  pageSize: 20,
  total: 0,
  hasMore: true,

  setActiveConversation: (id) => set({ activeConversationId: id }),

  fetchConversations: async (params = {}) => {
    set({ isLoading: true, error: null });
    try {
      const queryParams = new URLSearchParams();
      if (params.query) queryParams.append("query", params.query);
      if (params.tags) params.tags.forEach((tag) => queryParams.append("tags", tag));
      if (params.pinned !== undefined) queryParams.append("pinned", String(params.pinned));
      queryParams.append("page", String(params.page || 1));
      queryParams.append("page_size", String(params.page_size || get().pageSize));

      const response = await fetch(`${API_BASE}/api/v1/conversations?${queryParams}`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error("Failed to fetch conversations");
      }

      const data: ConversationListResponse = await response.json();
      set({
        conversations: data.conversations,
        total: data.total,
        page: data.page,
        hasMore: data.conversations.length >= get().pageSize,
        isLoading: false,
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Unknown error",
        isLoading: false,
      });
    }
  },

  createConversation: async (data = {}) => {
    const headers = getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/conversations`, {
      method: "POST",
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || "Failed to create conversation");
    }

    const conversation: Conversation = await response.json();
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      activeConversationId: conversation.id,
    }));
    return conversation;
  },

  updateConversation: async (id, data) => {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${id}`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      throw new Error("Failed to update conversation");
    }

    const updated: Conversation = await response.json();
    set((state) => ({
      conversations: state.conversations.map((c) => (c.id === id ? updated : c)),
    }));
  },

  deleteConversation: async (id) => {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${id}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error("Failed to delete conversation");
    }

    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      activeConversationId: state.activeConversationId === id ? null : state.activeConversationId,
    }));
  },

  togglePin: async (id, isPinned) => {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${id}/pin`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      body: JSON.stringify({ pinned: isPinned }),
    });

    if (!response.ok) {
      throw new Error("Failed to toggle pin");
    }

    const updated: Conversation = await response.json();
    set((state) => ({
      conversations: state.conversations.map((c) => (c.id === id ? updated : c)),
    }));
  },

  addTag: async (conversationId, tagName) => {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${conversationId}/tags`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ tag_name: tagName, color: "#6366f1" }),
    });

    if (!response.ok) {
      throw new Error("Failed to add tag");
    }

    const updated: Conversation = await response.json();
    set((state) => ({
      conversations: state.conversations.map((c) => (c.id === conversationId ? updated : c)),
    }));
  },

  removeTag: async (conversationId, tagName) => {
    const response = await fetch(
      `${API_BASE}/api/v1/conversations/${conversationId}/tags/${tagName}`,
      {
        method: "DELETE",
        headers: getAuthHeaders(),
      }
    );

    if (!response.ok) {
      throw new Error("Failed to remove tag");
    }

    // Remove tag from local state
    set((state) => ({
      conversations: state.conversations.map((c) => {
        if (c.id === conversationId) {
          return {
            ...c,
            tags: c.tags.filter((t) => t !== tagName),
          };
        }
        return c;
      }),
    }));
  },

  fetchTags: async () => {
    const response = await fetch(`${API_BASE}/api/v1/conversations/tags`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error("Failed to fetch tags");
    }

    const tags: ConversationTag[] = await response.json();
    set({ tags });
  },

  createTag: async (data) => {
    const response = await fetch(`${API_BASE}/api/v1/conversations/tags`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      throw new Error("Failed to create tag");
    }

    const tag: ConversationTag = await response.json();
    set((state) => ({ tags: [...state.tags, tag] }));
    return tag;
  },

  deleteTag: async (tagId) => {
    const response = await fetch(`${API_BASE}/api/v1/conversations/tags/${tagId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error("Failed to delete tag");
    }

    set((state) => ({
      tags: state.tags.filter((t) => t.id !== tagId),
    }));
  },

  setSearchQuery: (query) => set({ searchQuery: query }),

  setSelectedTags: (tags) => set({ selectedTags: tags }),

  setShowPinnedOnly: (show) => set({ showPinnedOnly: show }),

  resetFilters: () => {
    set({
      searchQuery: "",
      selectedTags: [],
      showPinnedOnly: false,
      page: 1,
    });
    get().fetchConversations();
  },

  loadMore: async () => {
    const { page, hasMore, isLoading } = get();
    if (!hasMore || isLoading) return;

    const nextPage = page + 1;
    const queryParams = getQueryParams(get());
    await get().fetchConversations({ ...queryParams, page: nextPage });
  },

  refresh: async () => {
    const queryParams = getQueryParams(get());
    await get().fetchConversations({ ...queryParams, page: 1 });
  },

  clear: () => {
    set({
      conversations: [],
      activeConversationId: null,
      tags: [],
      isLoading: false,
      error: null,
      searchQuery: "",
      selectedTags: [],
      showPinnedOnly: false,
      page: 1,
      total: 0,
      hasMore: true,
    });
  },
    }),
    {
      name: "conversation-storage",
      partialize: (state) => ({
        activeConversationId: state.activeConversationId,
      }),
    }
  )
);

function getQueryParams(state: ConversationStore): SearchConversationsParams {
  const params: SearchConversationsParams = {
    page: state.page,
    page_size: state.pageSize,
  };

  if (state.searchQuery) params.query = state.searchQuery;
  if (state.selectedTags.length > 0) params.tags = state.selectedTags;
  if (state.showPinnedOnly) params.pinned = true;

  return params;
}
