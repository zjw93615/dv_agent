/**
 * Documents Page
 * 
 * RAG document management interface
 */
import { useRagStore } from '../stores/ragStore';
import CollectionManager from '../components/rag/CollectionManager';
import DocumentUploader from '../components/rag/DocumentUploader';
import DocumentList from '../components/rag/DocumentList';
import SearchPanel from '../components/rag/SearchPanel';

export default function DocumentsPage() {
  const { collections, currentCollectionId } = useRagStore();

  // Find current collection
  const currentCollection = collections.find((c) => c.id === currentCollectionId);

  return (
    <div className="flex h-full bg-slate-900">
      {/* Sidebar - Collection Manager */}
      <CollectionManager />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="p-4 border-b border-slate-700">
          <h1 className="text-xl font-semibold text-white">
            {currentCollection ? currentCollection.name : '文档管理'}
          </h1>
          {currentCollection && (
            <p className="text-sm text-slate-400 mt-1">
              {currentCollection.document_count} 个文档 · 上传和管理您的知识库
            </p>
          )}
        </div>

        {/* Upload Area */}
        <div className="p-4 border-b border-slate-700">
          <DocumentUploader />
        </div>

        {/* Document List */}
        <div className="flex-1 overflow-y-auto p-4">
          <DocumentList />
        </div>

        {/* Search Panel */}
        <SearchPanel />
      </div>
    </div>
  );
}
