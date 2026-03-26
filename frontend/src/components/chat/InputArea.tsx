/**
 * Input Area Component
 * 
 * Chat input with send button
 */
import { useState, useRef, KeyboardEvent, useEffect } from 'react';
import { Send, Paperclip, Loader2 } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import { useSessionStore } from '../../stores/sessionStore';
import clsx from 'clsx';

export default function InputArea() {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  const { sendMessage, isSending } = useChatStore();
  const { currentSessionId, createSession } = useSessionStore();

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleSend = async () => {
    if (!input.trim() || isSending) return;

    const content = input.trim();
    setInput('');

    // Create session if none exists
    let sessionId = currentSessionId;
    if (!sessionId) {
      try {
        const session = await createSession({ title: content.slice(0, 50) });
        sessionId = session.id;
      } catch {
        return;
      }
    }

    // Send message
    await sendMessage(sessionId, content);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-slate-700 bg-slate-800/50 backdrop-blur-lg p-4">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-2">
          {/* Attachment Button (placeholder) */}
          <button
            className="p-2.5 text-slate-400 hover:text-slate-300 hover:bg-slate-700 rounded-lg transition"
            title="附加文件"
          >
            <Paperclip className="w-5 h-5" />
          </button>

          {/* Input */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息... (Shift+Enter 换行)"
              rows={1}
              disabled={isSending}
              className={clsx(
                'w-full px-4 py-3 bg-slate-700/50 border border-slate-600 rounded-xl',
                'text-white placeholder-slate-400 resize-none',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition'
              )}
            />
          </div>

          {/* Send Button */}
          <button
            onClick={handleSend}
            disabled={!input.trim() || isSending}
            className={clsx(
              'p-2.5 rounded-xl transition',
              input.trim() && !isSending
                ? 'bg-primary-600 hover:bg-primary-700 text-white'
                : 'bg-slate-700 text-slate-500 cursor-not-allowed'
            )}
          >
            {isSending ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Hint */}
        <p className="mt-2 text-xs text-slate-500 text-center">
          DV-Agent 可能会出错，请核实重要信息。
        </p>
      </div>
    </div>
  );
}
