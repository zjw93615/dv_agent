/**
 * Session API Client
 * 
 * API functions for session management
 */
import apiClient from '../lib/apiClient';

// Types
export interface Session {
  id: string;              // 映射自 session_id
  session_id?: string;     // 后端原始字段
  user_id: string;
  title: string;
  state?: string;
  message_count?: number;
  created_at: string;
  updated_at: string;
  last_active_at?: string;
  metadata?: Record<string, unknown>;
}

// 转换后端响应为前端格式
function normalizeSession(data: Record<string, unknown>): Session {
  return {
    id: (data.session_id || data.id) as string,
    session_id: data.session_id as string,
    user_id: data.user_id as string,
    title: (data.title || '新对话') as string,
    state: data.state as string,
    message_count: data.message_count as number,
    created_at: data.created_at as string,
    updated_at: data.updated_at as string,
    last_active_at: data.last_active_at as string,
    metadata: data.metadata as Record<string, unknown>,
  };
}

export interface CreateSessionRequest {
  title?: string;
  metadata?: Record<string, unknown>;
}

export interface UpdateSessionRequest {
  title?: string;
  metadata?: Record<string, unknown>;
}

export interface SessionListResponse {
  sessions: Session[];
  total: number;
}

interface RawSessionListResponse {
  sessions: Record<string, unknown>[];
  total: number;
}

// API functions
export const sessionApi = {
  /**
   * Get list of user sessions
   */
  list: async (limit = 50, offset = 0): Promise<SessionListResponse> => {
    const response = await apiClient.get<RawSessionListResponse>('/api/v1/sessions', {
      params: { limit, offset },
    });
    return {
      sessions: response.data.sessions.map(normalizeSession),
      total: response.data.total,
    };
  },

  /**
   * Get a specific session
   */
  get: async (sessionId: string): Promise<Session> => {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/sessions/${sessionId}`);
    return normalizeSession(response.data);
  },

  /**
   * Create a new session
   */
  create: async (data?: CreateSessionRequest): Promise<Session> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/sessions', data || {});
    return normalizeSession(response.data);
  },

  /**
   * Update a session
   */
  update: async (sessionId: string, data: UpdateSessionRequest): Promise<Session> => {
    const response = await apiClient.patch<Record<string, unknown>>(`/api/v1/sessions/${sessionId}`, data);
    return normalizeSession(response.data);
  },

  /**
   * Delete a session
   */
  delete: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/sessions/${sessionId}`);
  },
};

export default sessionApi;
