/** Shared TypeScript types for frontend-backend communication.
 *
 * These types must match the Pydantic models in backend/app/models.py
 *
 * References:
 * - D-15: Session ID uses UUID format
 * - D-16: Message storage with role, content, timestamp, token usage
 */

// WebSocket Message Types (matching backend WSMessage)
export interface WSMessage {
  type: "message" | "control";
  session_id: string;
  conversation_id?: string;
  user_id?: string;
  content?: string;
  control?: "stop" | "ping";
  // Image-related fields for multimodal support
  has_image?: boolean;
  image_data?: string;
}

// WebSocket Response Types (matching backend WSResponse)
export interface WSResponse {
  type: "delta" | "done" | "error";
  content?: string;
  error?: string;
  message_id?: string;
  conversation_id?: string;
  itinerary?: any;
}

// Database Models (matching backend MessageResponse, ConversationResponse)
export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tokens_used?: number;
  created_at: string;
  image?: {
    data: string;
    description?: string;
  };
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationWithMessages extends Conversation {
  messages: Message[];
}

// API Request/Response Types
export interface CreateConversationRequest {
  title?: string;
}

export interface CreateConversationResponse {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

// Context Window (matching backend ContextWindow)
export interface ContextWindow {
  messages: Array<{ role: string; content: string }>;
  total_tokens: number;
  message_count: number;
}

// Chat State for Frontend
export interface ChatState {
  messages: Message[];
  currentConversation: Conversation | null;
  isLoading: boolean;
  error: string | null;
}

// Itinerary Types
export interface ItineraryDay {
  date: string;
  activities: any[];
  weather_info?: any;
}

export interface Itinerary {
  id?: string;
  conversation_id?: string;
  destination: string;
  start_date: string;
  end_date: string;
  preferences?: string;
  travelers: number;
  budget?: string;
  days: ItineraryDay[];
  created_at?: string;
  updated_at?: string;
}
