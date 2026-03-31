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
