/**
 * RAG Store (Zustand)
 * 
 * Global state for RAG document management
 */
import { create } from 'zustand';
import { ragApi, Document, Collection } from '../api/rag.api';

interface UploadProgress {
  filename: string;
  progress: number;
  status: 'uploading' | 'processing' | 'completed' | 'failed';
  error?: string;
}

interface RagState {
  // State
  collections: Collection[];
  currentCollectionId: string | null;
  documents: Document[];
  uploadProgress: Map<string, UploadProgress>;
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchCollections: () => Promise<void>;
  createCollection: (name: string, description?: string) => Promise<Collection>;
  deleteCollection: (collectionId: string) => Promise<void>;
  setCurrentCollection: (collectionId: string | null) => void;
  fetchDocuments: (collectionId: string) => Promise<void>;
  uploadDocument: (file: File) => Promise<void>;
  deleteDocument: (documentId: string) => Promise<void>;
  updateDocumentStatus: (documentId: string, status: Document['status']) => void;
  clearError: () => void;
}

export const useRagStore = create<RagState>()((set, get) => ({
  // Initial state
  collections: [],
  currentCollectionId: null,
  documents: [],
  uploadProgress: new Map(),
  isLoading: false,
  error: null,

  // Fetch collections
  fetchCollections: async () => {
    set({ isLoading: true, error: null });
    try {
      const collections = await ragApi.listCollections();
      set({ collections, isLoading: false });
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '获取集合列表失败';
      set({ error: errorMessage, isLoading: false });
    }
  },

  // Create collection
  createCollection: async (name: string, description?: string) => {
    try {
      const collection = await ragApi.createCollection(name, description);
      set((state) => ({
        collections: [...state.collections, collection],
      }));
      return collection;
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '创建集合失败';
      set({ error: errorMessage });
      throw error;
    }
  },

  // Delete collection
  deleteCollection: async (collectionId: string) => {
    try {
      await ragApi.deleteCollection(collectionId);
      set((state) => ({
        collections: state.collections.filter((c) => c.id !== collectionId),
        currentCollectionId:
          state.currentCollectionId === collectionId ? null : state.currentCollectionId,
        documents: state.currentCollectionId === collectionId ? [] : state.documents,
      }));
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '删除集合失败';
      set({ error: errorMessage });
      throw error;
    }
  },

  // Set current collection
  setCurrentCollection: (collectionId: string | null) => {
    set({ currentCollectionId: collectionId, documents: [] });
    if (collectionId) {
      get().fetchDocuments(collectionId);
    }
  },

  // Fetch documents
  fetchDocuments: async (collectionId: string) => {
    set({ isLoading: true, error: null });
    try {
      const documents = await ragApi.listDocuments(collectionId);
      set({ documents, isLoading: false });
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '获取文档列表失败';
      set({ error: errorMessage, isLoading: false });
    }
  },

  // Upload document
  uploadDocument: async (file: File) => {
    const { currentCollectionId, uploadProgress } = get();
    if (!currentCollectionId) {
      set({ error: '请先选择一个集合' });
      return;
    }

    const fileKey = `${file.name}-${Date.now()}`;
    
    // Add to upload progress
    const newProgress = new Map(uploadProgress);
    newProgress.set(fileKey, {
      filename: file.name,
      progress: 0,
      status: 'uploading',
    });
    set({ uploadProgress: newProgress });

    try {
      await ragApi.uploadDocument(currentCollectionId, file, (progress) => {
        const updated = new Map(get().uploadProgress);
        const current = updated.get(fileKey);
        if (current) {
          updated.set(fileKey, { ...current, progress });
          set({ uploadProgress: updated });
        }
      });

      // Update status to processing
      const updated = new Map(get().uploadProgress);
      const current = updated.get(fileKey);
      if (current) {
        updated.set(fileKey, { ...current, progress: 100, status: 'processing' });
        set({ uploadProgress: updated });
      }

      // Refresh documents list
      await get().fetchDocuments(currentCollectionId);

      // Mark as completed
      const final = new Map(get().uploadProgress);
      const finalCurrent = final.get(fileKey);
      if (finalCurrent) {
        final.set(fileKey, { ...finalCurrent, status: 'completed' });
        set({ uploadProgress: final });
      }

      // Remove from progress after delay
      setTimeout(() => {
        const cleanup = new Map(get().uploadProgress);
        cleanup.delete(fileKey);
        set({ uploadProgress: cleanup });
      }, 3000);
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '上传失败';
      
      const updated = new Map(get().uploadProgress);
      const current = updated.get(fileKey);
      if (current) {
        updated.set(fileKey, { ...current, status: 'failed', error: errorMessage });
        set({ uploadProgress: updated });
      }
    }
  },

  // Delete document
  deleteDocument: async (documentId: string) => {
    const { currentCollectionId } = get();
    if (!currentCollectionId) return;

    try {
      await ragApi.deleteDocument(currentCollectionId, documentId);
      set((state) => ({
        documents: state.documents.filter((d) => d.id !== documentId),
      }));
    } catch (error: unknown) {
      const errorMessage =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '删除文档失败';
      set({ error: errorMessage });
      throw error;
    }
  },

  // Update document status (called from WebSocket)
  updateDocumentStatus: (documentId: string, status: Document['status']) => {
    set((state) => ({
      documents: state.documents.map((d) =>
        d.id === documentId ? { ...d, status } : d
      ),
    }));
  },

  // Clear error
  clearError: () => set({ error: null }),
}));

export default useRagStore;
