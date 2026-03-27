/**
 * WebSocket Manager
 * 
 * Manages WebSocket connection with auto-reconnect and heartbeat
 */
import { tokenManager } from './apiClient';

export type WSEventType = 
  | 'connected'
  | 'disconnected'
  | 'error'
  | 'heartbeat'
  | 'pong'
  | 'agent.thinking'
  | 'agent.stream'
  | 'agent.tool_call'
  | 'agent.tool_result'
  | 'agent.response'
  | 'agent.error'
  | 'agent.complete'
  | 'document.progress'
  | 'document.completed'
  | 'document.error'
  | 'session.update'
  | 'session.message';

export interface WSMessage {
  type: WSEventType;
  session_id?: string;
  data?: Record<string, unknown>;
  payload?: Record<string, unknown>;  // 后端使用 payload
  timestamp?: number;
}

export type WSEventHandler = (message: WSMessage) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private heartbeatTimeout = 30000;
  private handlers: Map<WSEventType | 'all', Set<WSEventHandler>> = new Map();
  private isConnecting = false;
  private shouldReconnect = true;

  constructor() {
    this.url = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:9080';
  }

  /**
   * Connect to WebSocket server
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    const token = tokenManager.getAccessToken();
    if (!token) {
      console.warn('[WS] No access token, cannot connect');
      return;
    }

    this.isConnecting = true;
    this.shouldReconnect = true;

    const wsUrl = `${this.url}/ws?token=${token}`;
    console.log('[WS] Connecting to', wsUrl.replace(token, '***'));

    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventHandlers();
    } catch (error) {
      console.error('[WS] Connection error:', error);
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.shouldReconnect = false;
    this.stopHeartbeat();
    
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.emit({ type: 'disconnected' });
  }

  /**
   * Subscribe to a session's events
   */
  subscribe(sessionId: string): void {
    this.send({
      type: 'subscribe',
      session_id: sessionId,
    });
  }

  /**
   * Unsubscribe from a session's events
   */
  unsubscribe(sessionId: string): void {
    this.send({
      type: 'unsubscribe',
      session_id: sessionId,
    });
  }

  /**
   * Send a message
   */
  send(message: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('[WS] Cannot send, connection not open');
    }
  }

  /**
   * Add event handler
   */
  on(event: WSEventType | 'all', handler: WSEventHandler): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.handlers.get(event)?.delete(handler);
    };
  }

  /**
   * Remove event handler
   */
  off(event: WSEventType | 'all', handler: WSEventHandler): void {
    this.handlers.get(event)?.delete(handler);
  }

  /**
   * Check if connected
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // Private methods

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[WS] Connected');
      this.isConnecting = false;
      this.reconnectAttempts = 0;
      this.startHeartbeat();
      this.emit({ type: 'connected' });
    };

    this.ws.onclose = (event) => {
      console.log('[WS] Disconnected:', event.code, event.reason);
      this.isConnecting = false;
      this.stopHeartbeat();
      this.emit({ type: 'disconnected' });

      if (this.shouldReconnect && event.code !== 1000) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error);
      this.emit({ type: 'error', data: error });
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WSMessage;
        this.handleMessage(message);
      } catch (error) {
        console.error('[WS] Failed to parse message:', error);
      }
    };
  }

  private handleMessage(message: WSMessage): void {
    // Handle heartbeat response
    if (message.type === 'heartbeat') {
      return;
    }

    // Emit to specific handlers
    this.emit(message);
  }

  private emit(message: WSMessage): void {
    // Call specific event handlers
    const handlers = this.handlers.get(message.type);
    if (handlers) {
      handlers.forEach((handler) => handler(message));
    }

    // Call 'all' handlers
    const allHandlers = this.handlers.get('all');
    if (allHandlers) {
      allHandlers.forEach((handler) => handler(message));
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    
    this.heartbeatInterval = setInterval(() => {
      this.send({ type: 'ping' });
    }, this.heartbeatTimeout);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WS] Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    setTimeout(() => {
      if (this.shouldReconnect) {
        this.connect();
      }
    }, delay);
  }
}

// Singleton instance
export const wsManager = new WebSocketManager();

export default wsManager;
