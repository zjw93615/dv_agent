/**
 * Chat Page
 * 
 * Main chat interface
 */
import { useEffect } from 'react';
import { useSessionStore } from '../stores/sessionStore';
import { useChatStore } from '../stores/chatStore';
import { useWebSocket } from '../hooks/useWebSocket';
import MessageList from '../components/chat/MessageList';
import InputArea from '../components/chat/InputArea';

export default function ChatPage() {
  const { currentSessionId } = useSessionStore();
  const { fetchHistory, clearMessages, appendStreamContent, finishStreaming, streamingContent } = useChatStore();
  const { isConnected, on } = useWebSocket({ sessionId: currentSessionId || undefined });

  // Fetch chat history when session changes
  useEffect(() => {
    if (currentSessionId) {
      fetchHistory(currentSessionId);
    } else {
      clearMessages();
    }
  }, [currentSessionId, fetchHistory, clearMessages]);

  // Listen for streaming responses from WebSocket
  useEffect(() => {
    // Handle thinking status
    const unsubThinking = on('agent.thinking', (msg) => {
      console.log('[WS] Agent thinking:', msg);
    });

    // Handle streaming content chunks
    const unsubStream = on('agent.stream', (msg) => {
      console.log('[WS] Agent stream:', msg);
      // session_id 在顶层, data 包含 content
      const sessionId = msg.session_id;
      const data = msg.data as { content?: string; done?: boolean } | undefined;
      if (sessionId === currentSessionId && data?.content) {
        appendStreamContent(data.content);
      }
    });

    // Handle final response
    const unsubResponse = on('agent.response', (msg) => {
      console.log('[WS] Agent response:', msg);
      const sessionId = msg.session_id;
      const data = msg.data as { content?: string; done?: boolean } | undefined;
      if (sessionId === currentSessionId && data?.done) {
        finishStreaming({
          id: `msg-${Date.now()}`,
          session_id: currentSessionId,
          role: 'assistant',
          content: data.content || '',
          created_at: new Date().toISOString(),
        });
      }
    });

    // Handle errors
    const unsubError = on('agent.error', (msg) => {
      console.log('[WS] Agent error:', msg);
      const sessionId = msg.session_id;
      const data = msg.data as { error?: string } | undefined;
      if (sessionId === currentSessionId && data?.error) {
        console.error('Agent error:', data.error);
        finishStreaming({
          id: `msg-${Date.now()}`,
          session_id: currentSessionId,
          role: 'assistant',
          content: `⚠️ 错误: ${data.error}`,
          created_at: new Date().toISOString(),
        });
      }
    });

    // Debug: log all WS messages
    const unsubAll = on('all', (msg) => {
      console.log('[WS] Message received:', msg.type, msg);
    });

    return () => {
      unsubThinking();
      unsubStream();
      unsubResponse();
      unsubError();
      unsubAll();
    };
  }, [on, currentSessionId, appendStreamContent, finishStreaming]);

  return (
    <div className="flex flex-col h-full bg-slate-900">
      {/* Messages (includes StreamingMessage and typing indicator) */}
      <MessageList />

      {/* WebSocket connection status (debug) */}
      {!isConnected && currentSessionId && (
        <div className="px-4 py-2 bg-yellow-500/10 text-yellow-400 text-xs text-center">
          ⚠️ WebSocket 未连接，实时消息可能无法接收
        </div>
      )}

      {/* Input */}
      <InputArea />
    </div>
  );
}
