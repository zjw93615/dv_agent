/**
 * Collection Manager Component
 * 
 * Sidebar for managing document collections
 */
import { useState, useEffect } from 'react';
import { FolderOpen, Plus, Trash2, Loader2 } from 'lucide-react';
import { useRagStore } from '../../stores/ragStore';
import { useRagWebSocket } from '../../hooks/useRagWebSocket';
import clsx from 'clsx';
import toast from 'react-hot-toast';

export default function CollectionManager() {
  const {
    collections,
    currentCollectionId,
    isLoading,
    fetchCollections,
    createCollection,
    deleteCollection,
    setCurrentCollection,
  } = useRagStore();

  // 注册 RAG WebSocket 事件处理
  useRagWebSocket();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Fetch collections on mount
  useEffect(() => {
    fetchCollections();
  }, [fetchCollections]);

  const handleCreate = async () => {
    if (!newName.trim()) {
      toast.error('请输入集合名称');
      return;
    }

    setIsCreating(true);
    try {
      const collection = await createCollection(newName.trim());
      setCurrentCollection(collection.id);
      setNewName('');
      setShowCreateForm(false);
      toast.success('集合创建成功');
    } catch {
      toast.error('创建集合失败');
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async (collectionId: string, name: string) => {
    if (confirm(`确定要删除集合 "${name}" 吗？此操作将删除所有文档且不可恢复。`)) {
      try {
        await deleteCollection(collectionId);
        toast.success('集合已删除');
      } catch {
        toast.error('删除集合失败');
      }
    }
  };

  return (
    <div className="w-64 bg-slate-800 border-r border-slate-700 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-slate-700">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-white">文档集合</h3>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition"
            title="新建集合"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>

        {/* Create Form */}
        {showCreateForm && (
          <div className="space-y-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="集合名称"
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-sm text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              autoFocus
            />
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                disabled={isCreating}
                className="flex-1 py-1.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-600/50 text-white text-sm rounded-lg transition"
              >
                {isCreating ? (
                  <Loader2 className="w-4 h-4 mx-auto animate-spin" />
                ) : (
                  '创建'
                )}
              </button>
              <button
                onClick={() => {
                  setShowCreateForm(false);
                  setNewName('');
                }}
                className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm rounded-lg transition"
              >
                取消
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Collection List */}
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading && collections.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
          </div>
        ) : collections.length === 0 ? (
          <div className="text-center py-8">
            <FolderOpen className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-sm text-slate-500">暂无集合</p>
            <p className="text-xs text-slate-600">点击上方 + 创建</p>
          </div>
        ) : (
          <div className="space-y-1">
            {collections.map((collection) => (
              <div
                key={collection.id}
                className={clsx(
                  'group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition',
                  currentCollectionId === collection.id
                    ? 'bg-primary-600/20 text-white'
                    : 'text-slate-300 hover:bg-slate-700/50'
                )}
                onClick={() => setCurrentCollection(collection.id)}
              >
                <FolderOpen className="w-4 h-4 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{collection.name}</p>
                  <p className="text-xs text-slate-500">{collection.document_count} 文档</p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(collection.id, collection.name);
                  }}
                  className="p-1 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
