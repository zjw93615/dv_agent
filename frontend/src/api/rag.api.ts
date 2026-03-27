/**
 * RAG API Client
 * 
 * API functions for document management and retrieval
 */
import apiClient from '../lib/apiClient';

// Types
export interface Document {
  id: string;
  collection_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  chunk_count?: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface Collection {
  id: string;  // 前端使用 id
  collection_id: string;  // 后端返回 collection_id
  name: string;
  description?: string;
  document_count: number;
  chunk_count?: number;
  created_at: string;
  metadata?: Record<string, unknown>;
}

// 转换函数：将后端响应转换为前端格式
const normalizeCollection = (c: Collection): Collection => ({
  ...c,
  id: c.collection_id || c.id,
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const normalizeDocument = (d: any): Document => ({
  ...d,
  id: d.document_id || d.id,
});

export interface UploadResponse {
  document_id: string;
  filename: string;
  status: string;
}

export interface SearchResult {
  document_id: string;
  chunk_id: string;
  content: string;
  score: number;
  metadata?: Record<string, unknown>;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
}

// API functions
export const ragApi = {
  // Collections
  listCollections: async (): Promise<Collection[]> => {
    const response = await apiClient.get<{ collections: Collection[] }>('/api/rag/collections');
    return response.data.collections.map(normalizeCollection);
  },

  createCollection: async (name: string, description?: string): Promise<Collection> => {
    const response = await apiClient.post<Collection>('/api/rag/collections', {
      name,
      description,
    });
    return normalizeCollection(response.data);
  },

  deleteCollection: async (collectionId: string): Promise<void> => {
    await apiClient.delete(`/api/rag/collections/${collectionId}`);
  },

  // Documents
  listDocuments: async (collectionId?: string): Promise<Document[]> => {
    const params = collectionId ? { collection_id: collectionId } : {};
    const response = await apiClient.get<{ documents: Document[] }>(
      '/api/rag/documents',
      { params }
    );
    return response.data.documents.map(normalizeDocument);
  },

  uploadDocument: async (
    collectionId: string | null,
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (collectionId) {
      formData.append('collection_id', collectionId);
    }

    const response = await apiClient.post<UploadResponse>(
      '/api/rag/documents/upload',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          if (onProgress && progressEvent.total) {
            const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            onProgress(progress);
          }
        },
      }
    );
    return response.data;
  },

  getDocument: async (documentId: string): Promise<Document> => {
    const response = await apiClient.get<Document>(
      `/api/rag/documents/${documentId}`
    );
    return response.data;
  },

  deleteDocument: async (_collectionId: string, documentId: string): Promise<void> => {
    await apiClient.delete(`/api/rag/documents/${documentId}`);
  },

  // Search
  search: async (
    query: string,
    collectionIds?: string[],
    limit = 10
  ): Promise<SearchResponse> => {
    const response = await apiClient.post<SearchResponse>(
      '/api/rag/search',
      { 
        query, 
        top_k: limit,
        collection_ids: collectionIds,
      }
    );
    return response.data;
  },
};

export default ragApi;
