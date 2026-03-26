/**
 * Message List Component
 * 
 * Displays list of chat messages with auto-scroll
 */
import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import MessageBubble from './MessageBubble';
import StreamingMessage from './StreamingMessage';

export default function MessageList() {
  const { messages, isLoading, isSending, streamingContent, streamingThinking, currentToolCalls } =
    useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
          <p className="text-slate-400 text-sm">加载聊天记录...</p>
        </div>
      </div>
    );
  }

  if (messages.length === 0 && !isSending) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md px-4">
          <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-primary-500 to-primary-700 rounded-2xl flex items-center justify-center">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <h3 className="text-xl font-semibold text-white mb-2">开始对话</h3>
          <p className="text-slate-400 text-sm">
            你可以问我任何问题，我会尽力帮助你。支持代码、文档、数据分析等多种任务。
          </p>
          <div className="mt-6 flex flex-wrap gap-2 justify-center">
            {['解释一段代码', '帮我写一个函数', '分析这个问题'].map((hint) => (
              <span
                key={hint}
                className="px-3 py-1.5 bg-slate-800 text-slate-300 text-sm rounded-full"
              >
                {hint}
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto py-4">
        {/* Messages */}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {/* Streaming Message */}
        {isSending && (streamingContent || streamingThinking || currentToolCalls.length > 0) && (
          <StreamingMessage
            content={streamingContent}
            thinking={streamingThinking}
            toolCalls={currentToolCalls}
          />
        )}

        {/* Typing Indicator (when waiting for response) */}
        {isSending && !streamingContent && !streamingThinking && (
          <div className="flex gap-3 py-4 px-4">
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
              <svg className="w-4 h-4 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="flex items-center">
              <div className="loading-dots flex gap-1">
                <span className="w-2 h-2 bg-slate-500 rounded-full" />
                <span className="w-2 h-2 bg-slate-500 rounded-full" />
                <span className="w-2 h-2 bg-slate-500 rounded-full" />
              </div>
            </div>
          </div>
        )}

        {/* Scroll anchor */}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
