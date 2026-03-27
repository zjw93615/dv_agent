/**
 * useRagWebSocket Hook
 * 
 * 处理 RAG 文档处理的 WebSocket 事件
 */
import { useEffect, useCallback } from 'react';
import { wsManager, WSMessage } from '../lib/websocket';
import useRagStore from '../stores/ragStore';

interface DocumentProgressData {
  document_id: string;
  stage: string;
  progress: number;
  message?: string;
}

interface DocumentCompletedData {
  document_id: string;
  filename: string;
  chunk_count: number;
  status: string;
}

interface DocumentErrorData {
  document_id: string;
  error: string;
  stage?: string;
  status: string;
}

export function useRagWebSocket() {
  const { 
    updateDocumentStatus, 
    fetchDocuments, 
    currentCollectionId,
    uploadProgress,
  } = useRagStore();

  // 处理文档进度更新
  const handleDocumentProgress = useCallback((message: WSMessage) => {
    const data = message.data as DocumentProgressData;
    if (!data?.document_id) return;

    console.log('[RAG WS] Document progress:', data);

    // 更新上传进度状态
    const { uploadProgress } = useRagStore.getState();
    
    // 查找对应的上传进度项
    for (const [key, progress] of uploadProgress.entries()) {
      if (progress.status === 'processing') {
        const updated = new Map(uploadProgress);
        updated.set(key, {
          ...progress,
          progress: Math.round(data.progress * 100),
          status: 'processing',
        });
        useRagStore.setState({ uploadProgress: updated });
        break;
      }
    }

    // 更新文档状态为 processing
    updateDocumentStatus(data.document_id, 'processing');
  }, [updateDocumentStatus]);

  // 处理文档完成
  const handleDocumentCompleted = useCallback((message: WSMessage) => {
    const data = message.data as DocumentCompletedData;
    if (!data?.document_id) return;

    console.log('[RAG WS] Document completed:', data);

    // 更新文档状态
    updateDocumentStatus(data.document_id, 'completed');

    // 刷新文档列表以获取最新数据
    const { currentCollectionId } = useRagStore.getState();
    if (currentCollectionId) {
      fetchDocuments(currentCollectionId);
    }

    // 更新上传进度为完成
    const { uploadProgress } = useRagStore.getState();
    for (const [key, progress] of uploadProgress.entries()) {
      if (progress.status === 'processing') {
        const updated = new Map(uploadProgress);
        updated.set(key, {
          ...progress,
          progress: 100,
          status: 'completed',
        });
        useRagStore.setState({ uploadProgress: updated });
        
        // 3秒后清除进度条
        setTimeout(() => {
          const cleanup = new Map(useRagStore.getState().uploadProgress);
          cleanup.delete(key);
          useRagStore.setState({ uploadProgress: cleanup });
        }, 3000);
        break;
      }
    }
  }, [updateDocumentStatus, fetchDocuments]);

  // 处理文档错误
  const handleDocumentError = useCallback((message: WSMessage) => {
    const data = message.data as DocumentErrorData;
    if (!data?.document_id) return;

    console.log('[RAG WS] Document error:', data);

    // 更新文档状态
    updateDocumentStatus(data.document_id, 'failed');

    // 更新上传进度为失败
    const { uploadProgress } = useRagStore.getState();
    for (const [key, progress] of uploadProgress.entries()) {
      if (progress.status === 'processing') {
        const updated = new Map(uploadProgress);
        updated.set(key, {
          ...progress,
          status: 'failed',
          error: data.error,
        });
        useRagStore.setState({ uploadProgress: updated });
        break;
      }
    }
  }, [updateDocumentStatus]);

  // 注册 WebSocket 事件处理器
  useEffect(() => {
    const unsubProgress = wsManager.on('document.progress', handleDocumentProgress);
    const unsubCompleted = wsManager.on('document.completed', handleDocumentCompleted);
    const unsubError = wsManager.on('document.error', handleDocumentError);

    return () => {
      unsubProgress();
      unsubCompleted();
      unsubError();
    };
  }, [handleDocumentProgress, handleDocumentCompleted, handleDocumentError]);

  return {
    // 可以返回一些有用的状态或方法
  };
}

export default useRagWebSocket;
