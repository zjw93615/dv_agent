/**
 * API Client Configuration
 * 
 * Axios instance with automatic token refresh and error handling
 */
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import toast from 'react-hot-toast';

// Create axios instance
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:9080',
  timeout: 30000,
  withCredentials: true, // Required for HttpOnly cookie (refresh token)
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token storage key
const ACCESS_TOKEN_KEY = 'dv_agent_access_token';

// Token management
export const tokenManager = {
  getAccessToken: (): string | null => {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },

  setAccessToken: (token: string): void => {
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
  },

  clearAccessToken: (): void => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
  },
};

// Flag to prevent multiple refresh requests
let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];

const subscribeTokenRefresh = (callback: (token: string) => void) => {
  refreshSubscribers.push(callback);
};

const onTokenRefreshed = (token: string) => {
  refreshSubscribers.forEach((callback) => callback(token));
  refreshSubscribers = [];
};

// Request interceptor - Add auth header
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = tokenManager.getAccessToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - Handle token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Skip refresh for auth endpoints
    if (
      originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/register') ||
      originalRequest.url?.includes('/auth/refresh')
    ) {
      return Promise.reject(error);
    }

    // Handle 401 Unauthorized - Try to refresh token
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // Wait for refresh to complete
        return new Promise((resolve) => {
          subscribeTokenRefresh((token: string) => {
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${token}`;
            }
            resolve(apiClient(originalRequest));
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Call refresh endpoint
        const response = await axios.post(
          `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:9080'}/auth/refresh`,
          {},
          { withCredentials: true }
        );

        const { access_token } = response.data;
        tokenManager.setAccessToken(access_token);
        onTokenRefreshed(access_token);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
        }

        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed - clear tokens and redirect to login
        tokenManager.clearAccessToken();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // Handle other errors
    if (error.response?.status === 403) {
      toast.error('您没有权限执行此操作');
    } else if (error.response?.status === 404) {
      toast.error('请求的资源不存在');
    } else if (error.response?.status === 429) {
      toast.error('请求过于频繁，请稍后再试');
    } else if (error.response?.status && error.response.status >= 500) {
      toast.error('服务器错误，请稍后重试');
    }

    return Promise.reject(error);
  }
);

export default apiClient;
