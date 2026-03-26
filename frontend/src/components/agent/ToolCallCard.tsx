/**
 * Tool Call Card Component
 * 
 * Displays a single tool call with status and results
 */
import { Wrench, Loader2, CheckCircle, XCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { ToolCall } from '../../api/chat.api';
import clsx from 'clsx';

interface ToolCallCardProps {
  toolCall: ToolCall;
}

export default function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);

  const statusConfig = {
    pending: {
      icon: <div className="w-3 h-3 bg-slate-400 rounded-full" />,
      text: '等待中',
      color: 'text-slate-400',
      bg: 'bg-slate-500/20',
    },
    running: {
      icon: <Loader2 className="w-3 h-3 animate-spin" />,
      text: '执行中',
      color: 'text-blue-400',
      bg: 'bg-blue-500/20',
    },
    completed: {
      icon: <CheckCircle className="w-3 h-3" />,
      text: '完成',
      color: 'text-green-400',
      bg: 'bg-green-500/20',
    },
    failed: {
      icon: <XCircle className="w-3 h-3" />,
      text: '失败',
      color: 'text-red-400',
      bg: 'bg-red-500/20',
    },
  };

  const status = statusConfig[toolCall.status];

  return (
    <div className="bg-slate-800/50 rounded-lg border border-slate-700 overflow-hidden animate-fade-in">
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-700/30 transition"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-slate-700 rounded-lg flex items-center justify-center">
            <Wrench className="w-4 h-4 text-slate-400" />
          </div>
          <div>
            <p className="text-sm font-medium text-white">{toolCall.name}</p>
            <p className="text-xs text-slate-500">工具调用</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={clsx(
              'flex items-center gap-1.5 px-2 py-1 rounded-full text-xs',
              status.color,
              status.bg
            )}
          >
            {status.icon}
            {status.text}
          </span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-500" />
          )}
        </div>
      </div>

      {/* Details */}
      {expanded && (
        <div className="border-t border-slate-700 p-3 space-y-3">
          {/* Arguments */}
          <div>
            <p className="text-xs font-medium text-slate-400 mb-1">参数</p>
            <pre className="p-2 bg-slate-900 rounded text-xs text-slate-300 overflow-x-auto">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {toolCall.result && (
            <div>
              <p className="text-xs font-medium text-slate-400 mb-1">结果</p>
              <pre className="p-2 bg-slate-900 rounded text-xs text-slate-300 overflow-x-auto max-h-48">
                {toolCall.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
