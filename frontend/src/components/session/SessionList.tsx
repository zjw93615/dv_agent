/**
 * Session List Component
 * 
 * Displays list of sessions in the sidebar
 */
import { useEffect } from 'react';
import { Plus, Loader2 } from 'lucide-react';
import { useSessionStore } from '../../stores/sessionStore';
import SessionItem from './SessionItem';
import toast from 'react-hot-toast';

export default function SessionList() {
  const {
    sessions,
    currentSessionId,
    isLoading,
    fetchSessions,
    createSession,
    setCurrentSession,
  } = useSessionStore();

  // Fetch sessions on mount
  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleCreateSession = async () => {
    try {
      await createSession({ title: '新对话' });
      toast.success('创建会话成功');
    } catch {
      toast.error('创建会话失败');
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* New Chat Button */}
      <div className="p-4">
        <button
          onClick={handleCreateSession}
          disabled={isLoading}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-600/50 text-white font-medium rounded-lg transition"
        >
          {isLoading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Plus className="w-5 h-5" />
          )}
          新对话
        </button>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto px-2">
        {isLoading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-slate-500 text-sm">暂无会话</p>
            <p className="text-slate-600 text-xs mt-1">点击上方按钮开始新对话</p>
          </div>
        ) : (
          <div className="space-y-1">
            {sessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === currentSessionId}
                onClick={() => setCurrentSession(session.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
