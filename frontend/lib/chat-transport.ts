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

import type { WSMessage, WSResponse } from "../../shared/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/chat";

interface TransportOptions {
  onChunk?: (chunk: string) => void;
  onDone?: (messageId: string) => void;
  onError?: (error: string) => void;
  onItinerary?: (itinerary: any) => void;
}

export class ChatWebSocketTransport {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private conversationId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private messageQueue: WSMessage[] = [];
  private isConnected = false;

  constructor(sessionId?: string) {
    this.sessionId = sessionId || this.generateSessionId();
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

        this.ws.onclose = (event) => {
          console.log("[ChatTransport] WebSocket disconnected", event.code, event.reason);
          this.isConnected = false;

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

      // Set up response handler
      const responseHandler = (event: MessageEvent) => {
        console.log("[ChatTransport] Received WebSocket response:", event.data);
        try {
          const response: WSResponse = JSON.parse(event.data);

          if (response.type === "delta" && response.content) {
            fullResponse += response.content;
            options.onChunk?.(response.content);
          } else if (response.type === "itinerary" && response.itinerary) {
            options.onItinerary?.(response.itinerary);
          } else if (response.type === "done") {
            // Remove the response handler
            this.ws?.removeEventListener("message", responseHandler);
            options.onDone?.(messageId);

            // Update conversation ID from response (use conversation_id field, not message_id)
            if (response.conversation_id) {
              this.conversationId = response.conversation_id;
              console.log("[ChatTransport] Updated conversation_id:", this.conversationId);
            }

            resolve(fullResponse);
          } else if (response.type === "error") {
            this.ws?.removeEventListener("message", responseHandler);
            options.onError?.(response.error || "Unknown error");
            reject(new Error(response.error || "Unknown error"));
          }
        } catch (error) {
          console.error("[ChatTransport] Failed to parse response:", error);
        }
      };

      // Add temporary message listener
      this.ws?.addEventListener("message", responseHandler);

      // Send the message
      this.send({
        type: "message",
        session_id: this.sessionId,
        conversation_id: this.conversationId || undefined,
        content,
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
}

// Factory function for creating transport instances
export function createChatTransport(sessionId?: string): ChatWebSocketTransport {
  const transport = new ChatWebSocketTransport(sessionId);
  transport.connect().catch(console.error);
  return transport;
}
