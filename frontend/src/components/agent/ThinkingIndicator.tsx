/**
 * Thinking Indicator Component
 * 
 * Shows agent's thinking process
 */
import { Brain } from 'lucide-react';
import clsx from 'clsx';

interface ThinkingIndicatorProps {
  content: string;
  isActive?: boolean;
}

export default function ThinkingIndicator({ content, isActive = true }: ThinkingIndicatorProps) {
  if (!content && !isActive) return null;

  return (
    <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700 animate-fade-in">
      <div className="flex items-center gap-2 mb-2">
        <div
          className={clsx(
            'w-6 h-6 rounded-full flex items-center justify-center',
            isActive ? 'bg-purple-500/20' : 'bg-slate-700'
          )}
        >
          <Brain
            className={clsx(
              'w-3.5 h-3.5',
              isActive ? 'text-purple-400 animate-pulse' : 'text-slate-500'
            )}
          />
        </div>
        <span className="text-xs font-medium text-slate-400">
          {isActive ? '思考中...' : '思考过程'}
        </span>
        {isActive && (
          <div className="flex gap-1">
            <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        )}
      </div>
      
      {content && (
        <div className="pl-8 text-sm text-slate-400 whitespace-pre-wrap leading-relaxed">
          {content}
        </div>
      )}
    </div>
  );
}
