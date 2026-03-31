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
  time: string; // "上午", "下午", "晚上"
  activity: string;
  location: string;
  description: string;
  duration: string;
  cost?: string;
}

export interface ItineraryDay {
  date: string;
  theme?: string;
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
