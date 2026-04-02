import type {
  Conversation,
  ConversationTag,
  ConversationListResponse,
  CreateConversationRequest,
  Message,
  UpdateConversationRequest,
  SearchConversationsParams,
  CreateTagRequest,
} from "../types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuthHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("auth-storage")
    ? JSON.parse(localStorage.getItem("auth-storage")!).state.token
    : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

function buildQueryParams(params: SearchConversationsParams): string {
  const query = new URLSearchParams();
  if (params.query) query.append("query", params.query);
  if (params.tags) params.tags.forEach((tag) => query.append("tags", tag));
  if (params.pinned !== undefined) query.append("pinned", String(params.pinned));
  query.append("page", String(params.page || 1));
  query.append("page_size", String(params.page_size || 20));
  return query.toString();
}

export const conversationsApi = {
  /**
   * List conversations with optional filters
   */
  async list(params?: SearchConversationsParams): Promise<ConversationListResponse> {
    const query = buildQueryParams(params || {});
    const response = await fetch(`${API_BASE}/api/v1/conversations?${query}`, {
      headers: getAuthHeaders(),
    });
    return handleResponse<ConversationListResponse>(response);
  },

  /**
   * Search conversations
   */
  async search(params: SearchConversationsParams): Promise<ConversationListResponse> {
    return this.list(params);
  },

  /**
   * Get a single conversation by ID
   */
  async get(id: string): Promise<Conversation> {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${id}`, {
      headers: getAuthHeaders(),
    });
    return handleResponse<Conversation>(response);
  },

  /**
   * Create a new conversation
   */
  async create(data?: CreateConversationRequest): Promise<Conversation> {
    const response = await fetch(`${API_BASE}/api/v1/conversations`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(data || {}),
    });
    return handleResponse<Conversation>(response);
  },

  /**
   * Update a conversation
   */
  async update(id: string, data: UpdateConversationRequest): Promise<Conversation> {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(data),
    });
    return handleResponse<Conversation>(response);
  },

  /**
   * Delete a conversation
   */
  async delete(id: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${id}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    return handleResponse<void>(response);
  },

  /**
   * Toggle conversation pin status
   */
  async togglePin(id: string, isPinned: boolean): Promise<Conversation> {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${id}/pin`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ pinned: isPinned }),
    });
    return handleResponse<Conversation>(response);
  },

  /**
   * Add a tag to a conversation
   */
  async addTag(conversationId: string, tagId: string): Promise<Conversation> {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${conversationId}/tags`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ tag_id: tagId }),
    });
    return handleResponse<Conversation>(response);
  },

  /**
   * Remove a tag from a conversation
   */
  async removeTag(conversationId: string, tagId: string): Promise<Conversation> {
    const response = await fetch(
      `${API_BASE}/api/v1/conversations/${conversationId}/tags/${tagId}`,
      {
        method: "DELETE",
        headers: getAuthHeaders(),
      }
    );
    return handleResponse<Conversation>(response);
  },

  /**
   * Get all conversation tags for the current user
   */
  async getConversationTags(): Promise<ConversationTag[]> {
    const response = await fetch(`${API_BASE}/api/v1/conversations/tags`, {
      headers: getAuthHeaders(),
    });
    return handleResponse<ConversationTag[]>(response);
  },

  /**
   * Get all tags for the current user
   */
  async getAllUserTags(): Promise<ConversationTag[]> {
    return this.getConversationTags();
  },

  /**
   * Create a new tag
   */
  async createTag(data: CreateTagRequest): Promise<ConversationTag> {
    const response = await fetch(`${API_BASE}/api/v1/conversations/tags`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(data),
    });
    return handleResponse<ConversationTag>(response);
  },

  /**
   * Delete a tag
   */
  async deleteTag(tagId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/v1/conversations/tags/${tagId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    return handleResponse<void>(response);
  },

  /**
   * Get messages for a conversation
   */
  async getMessages(conversationId: string, limit: number = 100): Promise<Message[]> {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages?limit=${limit}`, {
      headers: getAuthHeaders(),
    });
    const data = await handleResponse(response) as any[];
    // Convert backend format to frontend format
    return data.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      createdAt: new Date(m.created_at),
    }));
  },
};
