/**
 * Chat Store (Zustand)
 * 
 * Global state for chat messages
 */
import { create } from 'zustand';
import { chatApi, Message, ToolCall } from '../api/chat.api';

interface ChatState {
  // State
  messages: Message[];
  isLoading: boolean;
  isSending: boolean;
  error: string | null;
  streamingContent: string;
  streamingThinking: string;
  currentToolCalls: ToolCall[];

  // Actions
  fetchHistory: (sessionId: string) => Promise<void>;
  sendMessage: (sessionId: string, content: string) => Promise<void>;
  appendStreamContent: (content: string) => void;
  appendStreamThinking: (thinking: string) => void;
  updateToolCall: (toolCall: ToolCall) => void;
  finishStreaming: (message: Message) => void;
  clearMessages: () => void;
  clearError: () => void;
}

export const useChatStore = create<ChatState>()((set, get) => ({
  // Initial state
  messages: [],
  isLoading: false,
  isSending: false,
  error: null,
  streamingContent: '',
  streamingThinking: '',
  currentToolCalls: [],

  // Fetch chat history
  fetchHistory: async (sessionId: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await chatApi.getHistory(sessionId);
      set({ messages: response.messages, isLoading: false });
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '获取聊天记录失败';
      set({ error: errorMessage, isLoading: false });
    }
  },

  // Send a message
  sendMessage: async (sessionId: string, content: string) => {
    const userMessage: Message = {
      id: `temp-${Date.now()}`,
      session_id: sessionId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage],
      isSending: true,
      streamingContent: '',
      streamingThinking: '',
      currentToolCalls: [],
      error: null,
    }));

    try {
      // 发送消息到后端，后端会异步生成 LLM 响应并通过 WebSocket 推送
      // 这里不等待 LLM 响应，因为它是通过 WebSocket 流式返回的
      await chatApi.sendMessage(sessionId, { content });
      
      // 注意：不在这里设置 isSending: false
      // 等待 WebSocket 的 finishStreaming 来完成状态更新
      // 设置一个超时，如果 60 秒内没有收到响应，自动结束发送状态
      setTimeout(() => {
        const state = get();
        if (state.isSending) {
          set({ isSending: false });
        }
      }, 60000);
      
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '发送消息失败';
      set({ error: errorMessage, isSending: false });
    }
  },

  // Append streaming content
  appendStreamContent: (content: string) => {
    set((state) => ({
      streamingContent: state.streamingContent + content,
    }));
  },

  // Append streaming thinking
  appendStreamThinking: (thinking: string) => {
    set((state) => ({
      streamingThinking: state.streamingThinking + thinking,
    }));
  },

  // Update tool call status
  updateToolCall: (toolCall: ToolCall) => {
    set((state) => {
      const existing = state.currentToolCalls.find((tc) => tc.id === toolCall.id);
      if (existing) {
        return {
          currentToolCalls: state.currentToolCalls.map((tc) =>
            tc.id === toolCall.id ? toolCall : tc
          ),
        };
      }
      return {
        currentToolCalls: [...state.currentToolCalls, toolCall],
      };
    });
  },

  // Finish streaming and add complete message
  finishStreaming: (message: Message) => {
    set((state) => ({
      messages: [...state.messages, message],
      isSending: false,
      streamingContent: '',
      streamingThinking: '',
      currentToolCalls: [],
    }));
  },

  // Clear messages (when switching sessions)
  clearMessages: () => {
    set({
      messages: [],
      streamingContent: '',
      streamingThinking: '',
      currentToolCalls: [],
      error: null,
    });
  },

  // Clear error
  clearError: () => set({ error: null }),
}));

export default useChatStore;
