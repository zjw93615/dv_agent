/**
 * MessageBubble Component Tests
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '../utils';
import MessageBubble from '../../components/chat/MessageBubble';

describe('MessageBubble', () => {
  it('should render user message on the right', () => {
    render(
      <MessageBubble
        role="user"
        content="Hello, AI!"
        timestamp="2024-01-01T12:00:00Z"
      />
    );

    expect(screen.getByText('Hello, AI!')).toBeInTheDocument();
    // User messages should have justify-end class
    const container = screen.getByText('Hello, AI!').closest('div[class*="justify"]');
    expect(container?.className).toContain('justify-end');
  });

  it('should render assistant message on the left', () => {
    render(
      <MessageBubble
        role="assistant"
        content="Hello, human!"
        timestamp="2024-01-01T12:00:00Z"
      />
    );

    expect(screen.getByText('Hello, human!')).toBeInTheDocument();
    const container = screen.getByText('Hello, human!').closest('div[class*="justify"]');
    expect(container?.className).toContain('justify-start');
  });

  it('should render markdown content', () => {
    render(
      <MessageBubble
        role="assistant"
        content="**Bold text** and `code`"
        timestamp="2024-01-01T12:00:00Z"
      />
    );

    expect(screen.getByText('Bold text')).toBeInTheDocument();
    expect(screen.getByText('code')).toBeInTheDocument();
  });

  it('should show loading indicator when isLoading is true', () => {
    render(
      <MessageBubble
        role="assistant"
        content=""
        timestamp="2024-01-01T12:00:00Z"
        isLoading={true}
      />
    );

    // Should have loading dots
    expect(screen.getByTestId('loading-indicator') || document.querySelector('.animate-bounce')).toBeTruthy();
  });

  it('should display formatted timestamp', () => {
    render(
      <MessageBubble
        role="user"
        content="Test message"
        timestamp="2024-01-15T14:30:00Z"
      />
    );

    // Check if time is displayed (format depends on locale)
    const timeElement = document.querySelector('time, [class*="text-xs"]');
    expect(timeElement).toBeInTheDocument();
  });
});
