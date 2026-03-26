/**
 * Document List Component
 * 
 * Displays list of documents in current collection
 */
import { Loader2, FileText } from 'lucide-react';
import { useRagStore } from '../../stores/ragStore';
import DocumentItem from './DocumentItem';

export default function DocumentList() {
  const { documents, isLoading, currentCollectionId } = useRagStore();

  if (!currentCollectionId) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mb-4">
          <FileText className="w-8 h-8 text-slate-600" />
        </div>
        <p className="text-slate-400">请选择一个集合查看文档</p>
        <p className="text-sm text-slate-600 mt-1">或创建新的集合开始上传</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mb-4">
          <FileText className="w-8 h-8 text-slate-600" />
        </div>
        <p className="text-slate-400">此集合暂无文档</p>
        <p className="text-sm text-slate-600 mt-1">拖拽文件到上方区域开始上传</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <DocumentItem key={doc.id} document={doc} />
      ))}
    </div>
  );
}
