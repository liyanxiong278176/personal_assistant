/** Custom WebSocket transport for Vercel AI SDK.
 *
 * Implements the transport protocol to connect Vercel AI SDK's useChat hook
 * with the FastAPI backend WebSocket endpoint.
 *
 * References:
 * - D-07: Use native WebSocket for bidirectional communication
 * - D-09: WebSocket route /ws/chat
 * - RESEARCH.md: Vercel AI SDK transport pattern
 * - backend/app/api/chat.py: WebSocket protocol implementation
 */

import type { WSMessage, WSResponse, StageInfo } from "@/lib/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/chat";

interface TransportOptions {
  onChunk?: (chunk: string) => void;
  onDone?: (messageId: string) => void;
  onError?: (error: string) => void;
  onItinerary?: (itinerary: any) => void;
  onStage?: (stage: StageInfo) => void;  // 新增：阶段状态回调
  onTitleUpdate?: (conversationId: string, title: string) => void;  // 新增：标题更新回调
  userId?: string;
  imageData?: string;  // Base64 image data
}

export class ChatWebSocketTransport {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private userId: string | null = null;
  private conversationId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private messageQueue: WSMessage[] = [];
  private isConnected = false;
  // 当前活动的消息处理器（用于处理单次会话的响应）
  private currentResponseHandler: ((event: MessageEvent) => void) | null = null;
  // 标题更新回调（独立于 responseHandler，可以在 done 后继续处理）
  private _onTitleUpdateCallback: ((conversationId: string, title: string) => void) | null = null;

  constructor(sessionId?: string, userId?: string) {
    this.sessionId = sessionId || this.generateSessionId();
    this.userId = userId || null;
  }

  // 设置标题更新回调
  setTitleUpdateCallback(callback: (conversationId: string, title: string) => void): void {
    this._onTitleUpdateCallback = callback;
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(WS_URL);

        this.ws.onopen = () => {
          console.log("[ChatTransport] WebSocket connected");
          this.isConnected = true;
          this.reconnectAttempts = 0;

          // Send queued messages
          while (this.messageQueue.length > 0) {
            const msg = this.messageQueue.shift();
            if (msg) this.send(msg);
          }

          resolve();
        };

        // 设置全局消息处理器 - 委托给当前的 responseHandler，同时处理 title_update
        this.ws.onmessage = (event: MessageEvent) => {
          console.log("[ChatTransport] onmessage triggered, has currentResponseHandler:", !!this.currentResponseHandler);

          // 先尝试解析消息，处理 title_update 即使没有 responseHandler
          try {
            const response: WSResponse = JSON.parse(event.data);

            // title_update 消息即使没有 responseHandler 也需要处理
            if (response.type === "title_update" && response.conversation_id && response.content) {
              console.log("[ChatTransport] Title update received:", response.content);
              if (this._onTitleUpdateCallback) {
                this._onTitleUpdateCallback(response.conversation_id, response.content);
              }
              return;
            }
          } catch (e) {
            console.error("[ChatTransport] Failed to parse message:", e);
          }

          if (this.currentResponseHandler) {
            this.currentResponseHandler(event);
          } else {
            console.log("[ChatTransport] No currentResponseHandler, message ignored:", event.data);
          }
        };

        this.ws.onclose = (event) => {
          console.log("[ChatTransport] WebSocket disconnected", event.code, event.reason);
          this.isConnected = false;
          this.currentResponseHandler = null; // 清理处理器

          // Attempt reconnection for abnormal closures
          if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`[ChatTransport] Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            setTimeout(() => this.connect().catch(console.error), 1000 * this.reconnectAttempts);
          }
        };

        this.ws.onerror = (error) => {
          console.error("[ChatTransport] WebSocket error:", error);
          reject(error);
        };

      } catch (error) {
        reject(error);
      }
    });
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close(1000, "User disconnected");
      this.ws = null;
      this.isConnected = false;
    }
  }

  send(message: WSMessage): void {
    const msgWithSession = {
      ...message,
      session_id: message.session_id || this.sessionId,
      conversation_id: message.conversation_id || this.conversationId || undefined,
      user_id: message.user_id || this.userId || undefined,
    };

    console.log("[ChatTransport] send() called, isConnected:", this.isConnected, "readyState:", this.ws?.readyState);

    if (this.isConnected && this.ws?.readyState === WebSocket.OPEN) {
      console.log("[ChatTransport] Sending WebSocket data:", JSON.stringify(msgWithSession));
      this.ws.send(JSON.stringify(msgWithSession));
    } else {
      console.log("[ChatTransport] Queueing message (not connected)");
      this.messageQueue.push(msgWithSession);
    }
  }

  async sendMessage(
    content: string,
    options: TransportOptions = {}
  ): Promise<string> {
    console.log("[ChatTransport] sendMessage called, content:", content);
    console.log("[ChatTransport] isConnected:", this.isConnected, "ws.readyState:", this.ws?.readyState);
    console.log("[ChatTransport] has_image:", !!options.imageData);

    return new Promise((resolve, reject) => {
      if (!this.isConnected) {
        console.log("[ChatTransport] Not connected, connecting first...");
        this.connect().then(() => {
          console.log("[ChatTransport] Connected, retrying sendMessage");
          this.sendMessage(content, options).then(resolve).catch(reject);
        }).catch((err) => {
          console.error("[ChatTransport] Connection failed:", err);
          reject(err);
        });
        return;
      }

      const messageId = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
      let fullResponse = "";

      console.log("[ChatTransport] Sending WebSocket message:", messageId, content);

      // 清理之前的处理器（如果存在）
      if (this.currentResponseHandler) {
        console.log("[ChatTransport] Clearing previous responseHandler");
      }

      // 设置标题更新回调（独立于 responseHandler，可以在 done 后继续处理）
      if (options.onTitleUpdate) {
        this._onTitleUpdateCallback = options.onTitleUpdate;
      }

      // Set up response handler
      const responseHandler = (event: MessageEvent) => {
        console.log("[ChatTransport] responseHandler called, data:", event.data);
        try {
          const response: WSResponse = JSON.parse(event.data);

          if (response.type === "delta" && response.content) {
            fullResponse += response.content;
            options.onChunk?.(response.content);
          } else if (response.type === "stage" && response.stage) {
            // 处理阶段状态更新
            console.log("[ChatTransport] Stage update:", response.stage);
            options.onStage?.(response.stage);
          } else if (response.type === "itinerary" && response.itinerary) {
            options.onItinerary?.(response.itinerary);
          } else if (response.type === "title_update" && response.conversation_id && response.content) {
            // 处理标题更新
            console.log("[ChatTransport] Title update:", response.content);
            options.onTitleUpdate?.(response.conversation_id, response.content);
          } else if (response.type === "done") {
            // 清理当前的响应处理器
            this.currentResponseHandler = null;
            options.onDone?.(messageId);

            // Update conversation ID from response (use conversation_id field, not message_id)
            if (response.conversation_id) {
              this.conversationId = response.conversation_id;
              console.log("[ChatTransport] Updated conversation_id:", this.conversationId);
            }

            resolve(fullResponse);
          } else if (response.type === "error") {
            this.currentResponseHandler = null;
            options.onError?.(response.error || "Unknown error");
            reject(new Error(response.error || "Unknown error"));
          }
        } catch (error) {
          console.error("[ChatTransport] Failed to parse response:", error);
        }
      };

      // 设置当前的响应处理器（在发送消息之前）
      console.log("[ChatTransport] Setting currentResponseHandler");
      this.currentResponseHandler = responseHandler;

      // Send the message with optional image
      this.send({
        type: "message",
        session_id: this.sessionId,
        conversation_id: this.conversationId || undefined,
        user_id: this.userId || undefined,  // Include user_id for eval tracking
        content,
        has_image: !!options.imageData,
        image_data: options.imageData,
      });
    });
  }

  sendStop(): void {
    console.log("[ChatTransport] sendStop() called, sending stop signal");
    this.send({
      type: "control",
      session_id: this.sessionId,
      control: "stop",
    });
    console.log("[ChatTransport] Stop signal sent");
  }

  setConversationId(conversationId: string): void {
    this.conversationId = conversationId;
  }

  getConversationId(): string | null {
    return this.conversationId;
  }

  getSessionId(): string {
    return this.sessionId;
  }

  setUserId(userId: string): void {
    this.userId = userId;
  }

  getUserId(): string | null {
    return this.userId;
  }
}

// Factory function for creating transport instances
export function createChatTransport(sessionId?: string, userId?: string): ChatWebSocketTransport {
  const transport = new ChatWebSocketTransport(sessionId, userId);
  transport.connect().catch(console.error);
  return transport;
}
