/**
 * Agent Store (Zustand)
 * 
 * Global state for agent execution status
 */
import { create } from 'zustand';
import { ToolCall } from '../api/chat.api';

export type AgentStatus = 'idle' | 'thinking' | 'tool_calling' | 'responding' | 'complete' | 'error';

interface AgentState {
  // State
  status: AgentStatus;
  thinking: string;
  toolCalls: ToolCall[];
  currentSessionId: string | null;
  error: string | null;

  // Actions
  setStatus: (status: AgentStatus) => void;
  setThinking: (thinking: string) => void;
  appendThinking: (content: string) => void;
  addToolCall: (toolCall: ToolCall) => void;
  updateToolCall: (id: string, updates: Partial<ToolCall>) => void;
  setCurrentSession: (sessionId: string | null) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  status: 'idle' as AgentStatus,
  thinking: '',
  toolCalls: [],
  currentSessionId: null,
  error: null,
};

export const useAgentStore = create<AgentState>()((set) => ({
  ...initialState,

  setStatus: (status) => set({ status }),

  setThinking: (thinking) => set({ thinking }),

  appendThinking: (content) =>
    set((state) => ({ thinking: state.thinking + content })),

  addToolCall: (toolCall) =>
    set((state) => ({ toolCalls: [...state.toolCalls, toolCall] })),

  updateToolCall: (id, updates) =>
    set((state) => ({
      toolCalls: state.toolCalls.map((tc) =>
        tc.id === id ? { ...tc, ...updates } : tc
      ),
    })),

  setCurrentSession: (sessionId) => set({ currentSessionId: sessionId }),

  setError: (error) => set({ error, status: error ? 'error' : 'idle' }),

  reset: () => set(initialState),
}));

export default useAgentStore;
