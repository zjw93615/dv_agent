/**
 * Main Layout Component
 * 
 * App shell with sidebar
 */
import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Menu, X, LogOut, FileText, Settings, User, MessageSquare } from 'lucide-react';
import { useAuthStore } from '../../stores/authStore';
import SessionList from '../session/SessionList';
import clsx from 'clsx';

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const isDocumentsPage = location.pathname === '/documents';

  const handleLogout = async () => {
    await logout();
  };

  return (
    <div className="flex h-screen bg-slate-900">
      {/* Sidebar */}
      <aside
        className={clsx(
          'flex flex-col bg-slate-800 border-r border-slate-700 transition-all duration-300',
          sidebarOpen ? 'w-72' : 'w-0'
        )}
      >
        {sidebarOpen && (
          <>
            {/* Logo */}
            <div className="flex items-center justify-between h-16 px-4 border-b border-slate-700">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-700 rounded-lg flex items-center justify-center">
                  <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </div>
                <span className="text-lg font-semibold text-white">DV-Agent</span>
              </div>
            </div>

            {/* Session List */}
            <div className="flex-1 overflow-hidden">
              <SessionList />
            </div>

            {/* Bottom Menu */}
            <div className="border-t border-slate-700 p-2 space-y-1">
              <button 
                onClick={() => navigate('/')}
                className={clsx(
                  'w-full flex items-center gap-3 px-3 py-2 rounded-lg transition',
                  location.pathname === '/' 
                    ? 'text-white bg-slate-500' 
                    : 'text-slate-300 bg-slate-700 hover:bg-slate-700/50'
                )}
              >
                <MessageSquare className="w-4 h-4" />
                <span className="text-sm">对话</span>
              </button>
              <button 
                onClick={() => navigate('/documents')}
                className={clsx(
                  'w-full flex items-center gap-3 px-3 py-2 rounded-lg transition',
                  location.pathname === '/documents' 
                    ? 'text-white bg-slate-500' 
                    : 'text-slate-300 bg-slate-700 hover:bg-slate-700/50'
                )}
              >
                <FileText className="w-4 h-4" />
                <span className="text-sm">文档管理</span>
              </button>
              <button 
                onClick={() => navigate('/settings')}
                className={clsx(
                  'w-full flex items-center gap-3 px-3 py-2 rounded-lg transition',
                  location.pathname === '/settings' 
                    ? 'text-white bg-slate-500' 
                    : 'text-slate-300 bg-slate-700 hover:bg-slate-700/50'
                )}
              >
                <Settings className="w-4 h-4" />
                <span className="text-sm">设置</span>
              </button>
            </div>

            {/* User Section */}
            <div className="border-t border-slate-700 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-primary-600 rounded-full flex items-center justify-center">
                    <User className="w-4 h-4 text-white" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">
                      {user?.name || user?.email?.split('@')[0] || '用户'}
                    </p>
                    <p className="text-xs text-slate-500 truncate">{user?.email}</p>
                  </div>
                </div>
                <button
                  onClick={handleLogout}
                  className="p-2 text-white bg-slate-700 hover:text-red-400 hover:bg-slate-700 rounded-lg transition"
                  title="退出登录"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="flex items-center h-16 px-4 border-b border-slate-700 bg-slate-800/50">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition"
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-hidden">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
