/**
 * Message Bubble Component
 * 
 * Renders a single chat message with markdown support
 */
import { User, Bot, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '../../api/chat.api';
import clsx from 'clsx';

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Format time
  const formatTime = (dateString: string) => {
    return new Date(dateString).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div
      className={clsx(
        'group flex gap-3 py-4 px-4 hover:bg-slate-800/30 transition animate-fade-in',
        isUser ? 'flex-row-reverse' : ''
      )}
    >
      {/* Avatar */}
      <div
        className={clsx(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          isUser ? 'bg-primary-600' : 'bg-slate-700'
        )}
      >
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-slate-300" />
        )}
      </div>

      {/* Content */}
      <div className={clsx('flex-1 min-w-0', isUser ? 'text-right' : '')}>
        {/* Header */}
        <div className={clsx('flex items-center gap-2 mb-1', isUser ? 'justify-end' : '')}>
          <span className="text-sm font-medium text-slate-400">
            {isUser ? '你' : 'DV-Agent'}
          </span>
          <span className="text-xs text-slate-600">
            {formatTime(message.created_at)}
          </span>
        </div>

        {/* Message Content */}
        <div
          className={clsx(
            'inline-block max-w-[85%] rounded-2xl px-4 py-2.5 text-sm',
            isUser
              ? 'bg-primary-600 text-white rounded-tr-sm'
              : 'bg-slate-700 text-slate-100 rounded-tl-sm'
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // Custom code block rendering
                  code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const isInline = !match;
                    
                    if (isInline) {
                      return (
                        <code className="bg-slate-800 px-1.5 py-0.5 rounded text-sm" {...props}>
                          {children}
                        </code>
                      );
                    }

                    return (
                      <div className="relative group/code">
                        <div className="absolute right-2 top-2 opacity-0 group-hover/code:opacity-100 transition">
                          <button
                            onClick={() => navigator.clipboard.writeText(String(children))}
                            className="p-1.5 bg-slate-600 hover:bg-slate-500 rounded text-xs"
                          >
                            <Copy className="w-3 h-3" />
                          </button>
                        </div>
                        <code className={clsx('block p-3 rounded-lg bg-slate-800/80 overflow-x-auto text-sm', className)} {...props}>
                          {children}
                        </code>
                      </div>
                    );
                  },
                  // Custom link rendering
                  a({ href, children }) {
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary-400 hover:text-primary-300 underline"
                      >
                        {children}
                      </a>
                    );
                  },
                  // Custom table rendering
                  table({ children }) {
                    return (
                      <div className="overflow-x-auto my-2">
                        <table className="min-w-full border border-slate-600">
                          {children}
                        </table>
                      </div>
                    );
                  },
                  th({ children }) {
                    return (
                      <th className="border border-slate-600 px-3 py-2 bg-slate-700 text-left">
                        {children}
                      </th>
                    );
                  },
                  td({ children }) {
                    return (
                      <td className="border border-slate-600 px-3 py-2">
                        {children}
                      </td>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Copy Button (for assistant messages) */}
        {!isUser && (
          <div className="mt-1 opacity-0 group-hover:opacity-100 transition">
            <button
              onClick={handleCopy}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-slate-300 transition"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3" />
                  已复制
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  复制
                </>
              )}
            </button>
          </div>
        )}

        {/* Thinking Section (if available) */}
        {message.metadata?.thinking && (
          <details className="mt-2 text-xs">
            <summary className="text-slate-500 cursor-pointer hover:text-slate-400">
              查看思考过程
            </summary>
            <div className="mt-1 p-2 bg-slate-800/50 rounded text-slate-400 whitespace-pre-wrap">
              {message.metadata.thinking}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
