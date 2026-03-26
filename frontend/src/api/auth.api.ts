/**
 * Auth API Client
 * 
 * API functions for user authentication
 */
import apiClient, { tokenManager } from '../lib/apiClient';

// Request types
export interface RegisterRequest {
  email: string;
  password: string;
  name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

// Response types
export interface User {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// API functions
export const authApi = {
  /**
   * Register a new user
   */
  register: async (data: RegisterRequest): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>('/auth/register', data);
    // Store access token
    tokenManager.setAccessToken(response.data.access_token);
    return response.data;
  },

  /**
   * Login with email and password
   */
  login: async (data: LoginRequest): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>('/auth/login', data);
    // Store access token
    tokenManager.setAccessToken(response.data.access_token);
    return response.data;
  },

  /**
   * Refresh access token using HttpOnly cookie
   */
  refresh: async (): Promise<RefreshResponse> => {
    const response = await apiClient.post<RefreshResponse>('/auth/refresh');
    // Store new access token
    tokenManager.setAccessToken(response.data.access_token);
    return response.data;
  },

  /**
   * Logout - clear tokens and invalidate refresh token
   */
  logout: async (): Promise<void> => {
    try {
      await apiClient.post('/auth/logout');
    } finally {
      // Always clear access token
      tokenManager.clearAccessToken();
    }
  },

  /**
   * Get current user info
   */
  me: async (): Promise<User> => {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },
};

export default authApi;
