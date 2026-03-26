/**
 * Session Store Unit Tests
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSessionStore } from '../../stores/sessionStore';

// Mock session API
vi.mock('../../api/session.api', () => ({
  sessionApi: {
    list: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('useSessionStore', () => {
  beforeEach(() => {
    // Reset store state
    useSessionStore.setState({
      sessions: [],
      currentSessionId: null,
      isLoading: false,
    });
    vi.clearAllMocks();
  });

  it('should have initial state', () => {
    const state = useSessionStore.getState();
    expect(state.sessions).toEqual([]);
    expect(state.currentSessionId).toBeNull();
    expect(state.isLoading).toBe(false);
  });

  it('should set sessions', () => {
    const mockSessions = [
      { id: '1', title: 'Session 1', created_at: '2024-01-01', updated_at: '2024-01-01' },
      { id: '2', title: 'Session 2', created_at: '2024-01-02', updated_at: '2024-01-02' },
    ];

    useSessionStore.getState().setSessions(mockSessions);

    expect(useSessionStore.getState().sessions).toEqual(mockSessions);
  });

  it('should set current session', () => {
    useSessionStore.getState().setCurrentSession('session-123');
    expect(useSessionStore.getState().currentSessionId).toBe('session-123');
  });

  it('should add new session to the beginning', () => {
    const existingSession = { id: '1', title: 'Old', created_at: '2024-01-01', updated_at: '2024-01-01' };
    const newSession = { id: '2', title: 'New', created_at: '2024-01-02', updated_at: '2024-01-02' };

    useSessionStore.setState({ sessions: [existingSession] });
    useSessionStore.getState().addSession(newSession);

    const sessions = useSessionStore.getState().sessions;
    expect(sessions).toHaveLength(2);
    expect(sessions[0]).toEqual(newSession);
  });

  it('should remove session by id', () => {
    const sessions = [
      { id: '1', title: 'Session 1', created_at: '2024-01-01', updated_at: '2024-01-01' },
      { id: '2', title: 'Session 2', created_at: '2024-01-02', updated_at: '2024-01-02' },
    ];

    useSessionStore.setState({ sessions });
    useSessionStore.getState().removeSession('1');

    expect(useSessionStore.getState().sessions).toHaveLength(1);
    expect(useSessionStore.getState().sessions[0].id).toBe('2');
  });

  it('should clear current session when removed', () => {
    useSessionStore.setState({
      sessions: [{ id: '1', title: 'Session', created_at: '2024-01-01', updated_at: '2024-01-01' }],
      currentSessionId: '1',
    });

    useSessionStore.getState().removeSession('1');

    expect(useSessionStore.getState().currentSessionId).toBeNull();
  });

  it('should update session title', () => {
    const session = { id: '1', title: 'Old Title', created_at: '2024-01-01', updated_at: '2024-01-01' };
    useSessionStore.setState({ sessions: [session] });

    useSessionStore.getState().updateSession('1', { title: 'New Title' });

    expect(useSessionStore.getState().sessions[0].title).toBe('New Title');
  });
});
