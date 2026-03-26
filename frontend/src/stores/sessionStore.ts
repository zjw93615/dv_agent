/**
 * Session Store (Zustand)
 * 
 * Global state for session management
 */
import { create } from 'zustand';
import { sessionApi, Session, CreateSessionRequest, UpdateSessionRequest } from '../api/session.api';

interface SessionState {
  // State
  sessions: Session[];
  currentSessionId: string | null;
  isLoading: boolean;
  error: string | null;

  // Computed
  currentSession: Session | null;

  // Actions
  fetchSessions: () => Promise<void>;
  createSession: (data?: CreateSessionRequest) => Promise<Session>;
  updateSession: (sessionId: string, data: UpdateSessionRequest) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  setCurrentSession: (sessionId: string | null) => void;
  clearError: () => void;
}

export const useSessionStore = create<SessionState>()((set, get) => ({
  // Initial state
  sessions: [],
  currentSessionId: null,
  isLoading: false,
  error: null,

  // Computed getter for current session
  get currentSession() {
    const { sessions, currentSessionId } = get();
    return sessions.find((s) => s.id === currentSessionId) || null;
  },

  // Fetch all sessions
  fetchSessions: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await sessionApi.list();
      set({ sessions: response.sessions, isLoading: false });
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '获取会话列表失败';
      set({ error: errorMessage, isLoading: false });
    }
  },

  // Create a new session
  createSession: async (data?: CreateSessionRequest) => {
    set({ isLoading: true, error: null });
    try {
      const session = await sessionApi.create(data);
      set((state) => ({
        sessions: [session, ...state.sessions],
        currentSessionId: session.id,
        isLoading: false,
      }));
      return session;
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '创建会话失败';
      set({ error: errorMessage, isLoading: false });
      throw error;
    }
  },

  // Update a session
  updateSession: async (sessionId: string, data: UpdateSessionRequest) => {
    try {
      const updatedSession = await sessionApi.update(sessionId, data);
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? updatedSession : s
        ),
      }));
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '更新会话失败';
      set({ error: errorMessage });
      throw error;
    }
  },

  // Delete a session
  deleteSession: async (sessionId: string) => {
    try {
      await sessionApi.delete(sessionId);
      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== sessionId),
        currentSessionId:
          state.currentSessionId === sessionId ? null : state.currentSessionId,
      }));
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '删除会话失败';
      set({ error: errorMessage });
      throw error;
    }
  },

  // Set current session
  setCurrentSession: (sessionId: string | null) => {
    set({ currentSessionId: sessionId });
  },

  // Clear error
  clearError: () => set({ error: null }),
}));

export default useSessionStore;
