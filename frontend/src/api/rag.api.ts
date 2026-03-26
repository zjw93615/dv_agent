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
  id: string;
  name: string;
  description?: string;
  document_count: number;
  created_at: string;
  updated_at: string;
}

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
    return response.data.collections;
  },

  createCollection: async (name: string, description?: string): Promise<Collection> => {
    const response = await apiClient.post<Collection>('/api/rag/collections', {
      name,
      description,
    });
    return response.data;
  },

  deleteCollection: async (collectionId: string): Promise<void> => {
    await apiClient.delete(`/api/rag/collections/${collectionId}`);
  },

  // Documents
  listDocuments: async (collectionId: string): Promise<Document[]> => {
    const response = await apiClient.get<{ documents: Document[] }>(
      `/api/rag/collections/${collectionId}/documents`
    );
    return response.data.documents;
  },

  uploadDocument: async (
    collectionId: string,
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<UploadResponse>(
      `/api/rag/collections/${collectionId}/documents`,
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

  getDocument: async (collectionId: string, documentId: string): Promise<Document> => {
    const response = await apiClient.get<Document>(
      `/api/rag/collections/${collectionId}/documents/${documentId}`
    );
    return response.data;
  },

  deleteDocument: async (collectionId: string, documentId: string): Promise<void> => {
    await apiClient.delete(`/api/rag/collections/${collectionId}/documents/${documentId}`);
  },

  // Search
  search: async (
    collectionId: string,
    query: string,
    limit = 10
  ): Promise<SearchResponse> => {
    const response = await apiClient.post<SearchResponse>(
      `/api/rag/collections/${collectionId}/search`,
      { query, limit }
    );
    return response.data;
  },
};

export default ragApi;
