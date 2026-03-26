/**
 * Chat API Client
 * 
 * API functions for chat/conversation
 */
import apiClient from '../lib/apiClient';

// Types
export interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  metadata?: {
    thinking?: string;
    tool_calls?: ToolCall[];
    tokens?: {
      input: number;
      output: number;
    };
  };
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export interface SendMessageRequest {
  content: string;
  stream?: boolean;
}

export interface ChatHistoryResponse {
  messages: Message[];
  total: number;
}

// API functions
export const chatApi = {
  /**
   * Get chat history for a session
   */
  getHistory: async (sessionId: string, limit = 50, offset = 0): Promise<ChatHistoryResponse> => {
    const response = await apiClient.get<ChatHistoryResponse>(
      `/api/v1/sessions/${sessionId}/messages`,
      { params: { limit, offset } }
    );
    return response.data;
  },

  /**
   * Send a message (non-streaming)
   */
  sendMessage: async (sessionId: string, data: SendMessageRequest): Promise<Message> => {
    const response = await apiClient.post<Message>(
      `/api/v1/sessions/${sessionId}/messages`,
      data
    );
    return response.data;
  },

  /**
   * Send a message with streaming response
   * Returns an EventSource for SSE
   */
  sendMessageStream: (sessionId: string, content: string): EventSource => {
    const token = localStorage.getItem('dv_agent_access_token');
    const url = new URL(
      `/api/v1/sessions/${sessionId}/chat`,
      import.meta.env.VITE_API_BASE_URL || 'http://localhost:9080'
    );
    url.searchParams.set('content', encodeURIComponent(content));
    if (token) {
      url.searchParams.set('token', token);
    }
    
    return new EventSource(url.toString());
  },

  /**
   * Delete a message
   */
  deleteMessage: async (sessionId: string, messageId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/sessions/${sessionId}/messages/${messageId}`);
  },
};

export default chatApi;
