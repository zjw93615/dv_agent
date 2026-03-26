/**
 * Streaming Message Component
 * 
 * Renders a message that's being streamed in real-time
 */
import { Bot, Loader2, Wrench, CheckCircle, XCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ToolCall } from '../../api/chat.api';
import clsx from 'clsx';

interface StreamingMessageProps {
  content: string;
  thinking: string;
  toolCalls: ToolCall[];
}

export default function StreamingMessage({ content, thinking, toolCalls }: StreamingMessageProps) {
  return (
    <div className="flex gap-3 py-4 px-4 animate-fade-in">
      {/* Avatar */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
        <Bot className="w-4 h-4 text-slate-300" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-medium text-slate-400">DV-Agent</span>
          <span className="flex items-center gap-1 text-xs text-primary-400">
            <Loader2 className="w-3 h-3 animate-spin" />
            生成中...
          </span>
        </div>

        {/* Thinking Section */}
        {thinking && (
          <div className="mb-3 p-3 bg-slate-800/50 rounded-lg border border-slate-700">
            <div className="flex items-center gap-2 mb-2 text-xs text-slate-500">
              <div className="w-4 h-4 rounded-full border-2 border-slate-500 border-t-primary-400 animate-spin" />
              思考中...
            </div>
            <p className="text-sm text-slate-400 whitespace-pre-wrap">{thinking}</p>
          </div>
        )}

        {/* Tool Calls Section */}
        {toolCalls.length > 0 && (
          <div className="mb-3 space-y-2">
            {toolCalls.map((tc) => (
              <div
                key={tc.id}
                className="p-3 bg-slate-800/50 rounded-lg border border-slate-700"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Wrench className="w-4 h-4 text-slate-400" />
                  <span className="text-sm font-medium text-slate-300">{tc.name}</span>
                  <span
                    className={clsx(
                      'text-xs px-2 py-0.5 rounded-full',
                      tc.status === 'completed' && 'bg-green-500/20 text-green-400',
                      tc.status === 'running' && 'bg-blue-500/20 text-blue-400',
                      tc.status === 'failed' && 'bg-red-500/20 text-red-400',
                      tc.status === 'pending' && 'bg-slate-500/20 text-slate-400'
                    )}
                  >
                    {tc.status === 'completed' && (
                      <span className="flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" /> 完成
                      </span>
                    )}
                    {tc.status === 'running' && (
                      <span className="flex items-center gap-1">
                        <Loader2 className="w-3 h-3 animate-spin" /> 执行中
                      </span>
                    )}
                    {tc.status === 'failed' && (
                      <span className="flex items-center gap-1">
                        <XCircle className="w-3 h-3" /> 失败
                      </span>
                    )}
                    {tc.status === 'pending' && '等待'}
                  </span>
                </div>

                {/* Arguments */}
                <details className="text-xs">
                  <summary className="text-slate-500 cursor-pointer hover:text-slate-400">
                    查看参数
                  </summary>
                  <pre className="mt-1 p-2 bg-slate-900 rounded text-slate-400 overflow-x-auto">
                    {JSON.stringify(tc.arguments, null, 2)}
                  </pre>
                </details>

                {/* Result */}
                {tc.result && (
                  <details className="mt-2 text-xs">
                    <summary className="text-slate-500 cursor-pointer hover:text-slate-400">
                      查看结果
                    </summary>
                    <pre className="mt-1 p-2 bg-slate-900 rounded text-slate-400 overflow-x-auto max-h-32">
                      {tc.result}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Content */}
        {content && (
          <div className="inline-block max-w-[85%] rounded-2xl rounded-tl-sm px-4 py-2.5 bg-slate-700 text-slate-100 text-sm">
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
            {/* Cursor */}
            <span className="inline-block w-2 h-4 ml-0.5 bg-primary-400 animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
}
