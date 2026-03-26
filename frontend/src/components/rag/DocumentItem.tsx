/**
 * Document Item Component
 * 
 * Single document item with status and actions
 */
import { FileText, Trash2, Loader2, CheckCircle, AlertCircle, Clock } from 'lucide-react';
import { Document } from '../../api/rag.api';
import { useRagStore } from '../../stores/ragStore';
import clsx from 'clsx';

interface DocumentItemProps {
  document: Document;
}

export default function DocumentItem({ document }: DocumentItemProps) {
  const { deleteDocument } = useRagStore();

  const handleDelete = async () => {
    if (confirm(`确定要删除 "${document.filename}" 吗？`)) {
      await deleteDocument(document.id);
    }
  };

  // Format file size
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Status config
  const statusConfig = {
    pending: {
      icon: <Clock className="w-4 h-4" />,
      text: '等待处理',
      color: 'text-slate-400',
      bg: 'bg-slate-500/20',
    },
    processing: {
      icon: <Loader2 className="w-4 h-4 animate-spin" />,
      text: '处理中',
      color: 'text-yellow-400',
      bg: 'bg-yellow-500/20',
    },
    completed: {
      icon: <CheckCircle className="w-4 h-4" />,
      text: '已完成',
      color: 'text-green-400',
      bg: 'bg-green-500/20',
    },
    failed: {
      icon: <AlertCircle className="w-4 h-4" />,
      text: '处理失败',
      color: 'text-red-400',
      bg: 'bg-red-500/20',
    },
  };

  const status = statusConfig[document.status];

  // Get file icon based on type
  const getFileIcon = () => {
    const ext = document.filename.split('.').pop()?.toLowerCase();
    const colors: Record<string, string> = {
      pdf: 'text-red-400',
      doc: 'text-blue-400',
      docx: 'text-blue-400',
      txt: 'text-slate-400',
      md: 'text-purple-400',
    };
    return colors[ext || ''] || 'text-slate-400';
  };

  return (
    <div className="group flex items-center gap-3 p-3 bg-slate-800/50 hover:bg-slate-800 rounded-lg border border-slate-700 transition">
      {/* File Icon */}
      <div className="w-10 h-10 bg-slate-700 rounded-lg flex items-center justify-center">
        <FileText className={clsx('w-5 h-5', getFileIcon())} />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">{document.filename}</p>
        <div className="flex items-center gap-3 mt-0.5">
          <span className="text-xs text-slate-500">{formatSize(document.file_size)}</span>
          <span className="text-xs text-slate-600">•</span>
          <span className="text-xs text-slate-500">{formatDate(document.created_at)}</span>
          {document.chunk_count !== undefined && (
            <>
              <span className="text-xs text-slate-600">•</span>
              <span className="text-xs text-slate-500">{document.chunk_count} 个片段</span>
            </>
          )}
        </div>
      </div>

      {/* Status Badge */}
      <div
        className={clsx(
          'flex items-center gap-1.5 px-2 py-1 rounded-full text-xs',
          status.color,
          status.bg
        )}
      >
        {status.icon}
        <span>{status.text}</span>
      </div>

      {/* Delete Button */}
      <button
        onClick={handleDelete}
        className="p-2 text-slate-500 hover:text-red-400 hover:bg-slate-700 rounded-lg opacity-0 group-hover:opacity-100 transition"
        title="删除文档"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}
