/**
 * useWebSocket Hook
 * 
 * React hook for WebSocket connection management
 */
import { useEffect, useCallback, useState } from 'react';
import { wsManager, WSMessage, WSEventType, WSEventHandler } from '../lib/websocket';
import { useAuthStore } from '../stores/authStore';

interface UseWebSocketOptions {
  autoConnect?: boolean;
  sessionId?: string;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  connect: () => void;
  disconnect: () => void;
  subscribe: (sessionId: string) => void;
  unsubscribe: (sessionId: string) => void;
  on: (event: WSEventType | 'all', handler: WSEventHandler) => () => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { autoConnect = true, sessionId } = options;
  const { isAuthenticated } = useAuthStore();
  const [isConnected, setIsConnected] = useState(wsManager.isConnected);

  // Handle connection state changes
  useEffect(() => {
    const handleConnected = () => setIsConnected(true);
    const handleDisconnected = () => setIsConnected(false);

    const unsubConnected = wsManager.on('connected', handleConnected);
    const unsubDisconnected = wsManager.on('disconnected', handleDisconnected);

    return () => {
      unsubConnected();
      unsubDisconnected();
    };
  }, []);

  // Auto-connect when authenticated
  useEffect(() => {
    if (autoConnect && isAuthenticated) {
      wsManager.connect();
    }

    return () => {
      // Don't disconnect on cleanup - let the manager handle reconnection
    };
  }, [autoConnect, isAuthenticated]);

  // Auto-subscribe to session
  useEffect(() => {
    if (sessionId && isConnected) {
      wsManager.subscribe(sessionId);
      
      return () => {
        wsManager.unsubscribe(sessionId);
      };
    }
  }, [sessionId, isConnected]);

  const connect = useCallback(() => {
    wsManager.connect();
  }, []);

  const disconnect = useCallback(() => {
    wsManager.disconnect();
  }, []);

  const subscribe = useCallback((sid: string) => {
    wsManager.subscribe(sid);
  }, []);

  const unsubscribe = useCallback((sid: string) => {
    wsManager.unsubscribe(sid);
  }, []);

  const on = useCallback((event: WSEventType | 'all', handler: WSEventHandler) => {
    return wsManager.on(event, handler);
  }, []);

  return {
    isConnected,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    on,
  };
}

export default useWebSocket;
