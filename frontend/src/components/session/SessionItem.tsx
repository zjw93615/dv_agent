/**
 * Session Item Component
 * 
 * Single session item in the sidebar
 */
import { useState } from 'react';
import { MessageSquare, MoreVertical, Trash2, Edit2 } from 'lucide-react';
import { Session } from '../../api/session.api';
import { useSessionStore } from '../../stores/sessionStore';
import clsx from 'clsx';

interface SessionItemProps {
  session: Session;
  isActive: boolean;
  onClick: () => void;
}

export default function SessionItem({ session, isActive, onClick }: SessionItemProps) {
  const { deleteSession, updateSession } = useSessionStore();
  const [showMenu, setShowMenu] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(session.title);

  // Format date
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) return '今天';
    if (diffDays === 1) return '昨天';
    if (diffDays < 7) return `${diffDays}天前`;
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('确定要删除这个会话吗？')) {
      await deleteSession(session.id);
    }
    setShowMenu(false);
  };

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsEditing(true);
    setShowMenu(false);
  };

  const handleSaveTitle = async () => {
    if (editTitle.trim() && editTitle !== session.title) {
      await updateSession(session.id, { title: editTitle.trim() });
    }
    setIsEditing(false);
  };

  return (
    <div
      className={clsx(
        'group relative flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition',
        isActive
          ? 'bg-primary-600/20 text-white'
          : 'hover:bg-slate-700/50 text-slate-300'
      )}
      onClick={onClick}
    >
      <MessageSquare className="w-4 h-4 flex-shrink-0" />
      
      <div className="flex-1 min-w-0">
        {isEditing ? (
          <input
            type="text"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onBlur={handleSaveTitle}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSaveTitle();
              if (e.key === 'Escape') setIsEditing(false);
            }}
            onClick={(e) => e.stopPropagation()}
            className="w-full bg-slate-700 px-2 py-0.5 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
            autoFocus
          />
        ) : (
          <p className="text-sm truncate">{session.title || '新对话'}</p>
        )}
        <p className="text-xs text-slate-500 truncate">
          {formatDate(session.updated_at)}
        </p>
      </div>

      {/* Menu Button */}
      <div className="relative">
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowMenu(!showMenu);
          }}
          className={clsx(
            'p-1 rounded hover:bg-slate-600 transition',
            showMenu ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
          )}
        >
          <MoreVertical className="w-4 h-4" />
        </button>

        {/* Dropdown Menu */}
        {showMenu && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={(e) => {
                e.stopPropagation();
                setShowMenu(false);
              }}
            />
            <div className="absolute right-0 top-full mt-1 z-20 bg-slate-700 rounded-lg shadow-lg border border-slate-600 py-1 min-w-[120px]">
              <button
                onClick={handleEdit}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 transition"
              >
                <Edit2 className="w-4 h-4" />
                重命名
              </button>
              <button
                onClick={handleDelete}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-slate-600 transition"
              >
                <Trash2 className="w-4 h-4" />
                删除
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
