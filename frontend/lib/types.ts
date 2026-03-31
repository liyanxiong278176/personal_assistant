export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt?: Date;
  itinerary?: Itinerary;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

export interface ChatRequest {
  message: string;
  conversationId?: string;
  sessionId: string;
}

export interface ChatResponse {
  type: "delta" | "done" | "error";
  content?: string;
  error?: string;
}

// Itinerary types
export interface ItineraryRequest {
  conversation_id: string;
  destination: string;
  start_date: string;
  end_date: string;
  preferences?: string;
  travelers?: number;
  budget?: "low" | "medium" | "high";
}

export interface ItineraryActivity {
  time: string; // "08:00-11:00" or "上午"
  period?: string; // "清晨", "上午", "中午", "下午", "傍晚", "晚上"
  activity: string;
  location: string;
  description: string; // 详细描述，包含推荐理由、交通、注意事项等
  duration: string;
  cost?: string;
}

export interface ItineraryDay {
  date: string;
  theme?: string;
  summary?: string; // 今日亮点
  weather_note?: string; // 天气穿衣建议
  weather?: {
    temp_max?: string;
    temp_min?: string;
    condition: string;
  };
  activities: ItineraryActivity[];
}

export interface Itinerary {
  id: string;
  destination: string;
  overview?: string; // 整体行程概述
  tips?: string[]; // 实用提示
  start_date: string;
  end_date: string;
  preferences?: string;
  travelers?: number;
  budget?: string;
  days: ItineraryDay[];
}

export interface MapLocation {
  name: string;
  lng: number;
  lat: number;
  description?: string;
}

// ============ Auth Types ============

export interface User {
  id: string;
  email: string;
  username?: string;
  avatar_url?: string;
  created_at: string;
  updated_at: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface LoginRequest {
  email: string;
  code: string;
}

export interface RegisterRequest {
  email: string;
  password?: string;
  username?: string;
}

export interface SendCodeRequest {
  email: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

// ============ Conversation Types ============

export interface ConversationTag {
  id: string;
  name: string;
  color?: string;
  user_id: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  user_id: string;
  title: string;
  is_pinned: boolean;
  tags: ConversationTag[];
  created_at: string;
  updated_at: string;
  message_count?: number;
  last_message_at?: string;
  preview?: string;
}

export interface ConversationUpdate {
  title?: string;
  is_pinned?: boolean;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateConversationRequest {
  title?: string;
  initial_message?: string;
}

export interface UpdateConversationRequest {
  title?: string;
  is_pinned?: boolean;
}

export interface SearchConversationsParams {
  query?: string;
  tags?: string[];
  is_pinned?: boolean;
  page?: number;
  page_size?: number;
}

export interface TogglePinRequest {
  is_pinned: boolean;
}

export interface AddTagRequest {
  tag_id: string;
}

export interface RemoveTagRequest {
  tag_id: string;
}

export interface CreateTagRequest {
  name: string;
  color?: string;
}

export interface MessageAction {
  type: "copy" | "regenerate" | "delete";
  messageId: string;
}
