/**
 * Agent Execution Panel Component
 * 
 * Shows real-time agent execution status with thinking and tool calls
 */
import { useEffect } from 'react';
import { Cpu, Wifi, WifiOff } from 'lucide-react';
import { useAgentStore } from '../../stores/agentStore';
import { useWebSocket } from '../../hooks/useWebSocket';
import { useSessionStore } from '../../stores/sessionStore';
import ThinkingIndicator from './ThinkingIndicator';
import ToolCallCard from './ToolCallCard';
import clsx from 'clsx';

export default function AgentExecutionPanel() {
  const { status, thinking, toolCalls, reset } = useAgentStore();
  const { currentSessionId } = useSessionStore();
  const { isConnected, on } = useWebSocket({ sessionId: currentSessionId || undefined });

  // Listen to WebSocket events
  useEffect(() => {
    const unsubThinking = on('agent.thinking', (msg) => {
      useAgentStore.getState().setStatus('thinking');
      useAgentStore.getState().appendThinking(msg.data as string);
    });

    const unsubToolCall = on('agent.tool_call', (msg) => {
      useAgentStore.getState().setStatus('tool_calling');
      useAgentStore.getState().addToolCall(msg.data as never);
    });

    const unsubToolResult = on('agent.tool_result', (msg) => {
      const data = msg.data as { id: string; result: string; status: string };
      useAgentStore.getState().updateToolCall(data.id, {
        result: data.result,
        status: data.status as never,
      });
    });

    const unsubResponse = on('agent.response', () => {
      useAgentStore.getState().setStatus('responding');
    });

    const unsubComplete = on('agent.complete', () => {
      useAgentStore.getState().setStatus('complete');
      // Reset after a delay
      setTimeout(() => reset(), 3000);
    });

    return () => {
      unsubThinking();
      unsubToolCall();
      unsubToolResult();
      unsubResponse();
      unsubComplete();
    };
  }, [on, reset]);

  // Don't show if idle
  if (status === 'idle' && !thinking && toolCalls.length === 0) {
    return null;
  }

  return (
    <div className="border-t border-slate-700 bg-slate-800/30 p-4 animate-fade-in">
      <div className="max-w-3xl mx-auto space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={clsx(
                'w-8 h-8 rounded-lg flex items-center justify-center',
                status === 'idle' || status === 'complete'
                  ? 'bg-slate-700'
                  : 'bg-primary-600/20'
              )}
            >
              <Cpu
                className={clsx(
                  'w-4 h-4',
                  status === 'idle' || status === 'complete'
                    ? 'text-slate-500'
                    : 'text-primary-400 animate-pulse'
                )}
              />
            </div>
            <div>
              <p className="text-sm font-medium text-white">Agent 执行状态</p>
              <p className="text-xs text-slate-500">
                {status === 'thinking' && '正在思考...'}
                {status === 'tool_calling' && '正在调用工具...'}
                {status === 'responding' && '正在生成回复...'}
                {status === 'complete' && '执行完成'}
                {status === 'error' && '执行出错'}
                {status === 'idle' && '空闲'}
              </p>
            </div>
          </div>

          {/* Connection Status */}
          <div
            className={clsx(
              'flex items-center gap-1.5 px-2 py-1 rounded-full text-xs',
              isConnected ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
            )}
          >
            {isConnected ? (
              <>
                <Wifi className="w-3 h-3" />
                已连接
              </>
            ) : (
              <>
                <WifiOff className="w-3 h-3" />
                已断开
              </>
            )}
          </div>
        </div>

        {/* Thinking */}
        {thinking && (
          <ThinkingIndicator
            content={thinking}
            isActive={status === 'thinking'}
          />
        )}

        {/* Tool Calls */}
        {toolCalls.length > 0 && (
          <div className="space-y-2">
            {toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
