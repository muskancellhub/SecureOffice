import { Bot, Send, X, Minimize2 } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { askChatbot, type ChatMessage } from '../api/chatbotApi';

/**
 * Lightweight markdown renderer for chat messages.
 * Handles: [links](/path), **bold**, bullet points (• or -), and newlines.
 */
function renderMarkdown(text: string, onNavigate: (path: string) => void): React.ReactNode[] {
  const lines = text.split('\n');
  return lines.map((line, lineIdx) => {
    const isBullet = /^\s*[-•]\s+/.test(line);
    const cleanLine = isBullet ? line.replace(/^\s*[-•]\s+/, '') : line;

    // Parse inline: [text](url) and **bold**
    const parts: React.ReactNode[] = [];
    const inlineRegex = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*/g;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = inlineRegex.exec(cleanLine)) !== null) {
      // Text before match
      if (match.index > lastIndex) {
        parts.push(cleanLine.slice(lastIndex, match.index));
      }

      if (match[1] && match[2]) {
        // Markdown link: [text](url)
        const linkText = match[1];
        const href = match[2];
        const isInternal = href.startsWith('/');
        parts.push(
          <a
            key={`${lineIdx}-${match.index}`}
            href={href}
            className="chatbot-link"
            onClick={(e) => {
              if (isInternal) {
                e.preventDefault();
                onNavigate(href);
              }
            }}
            {...(!isInternal ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
          >
            {linkText}
          </a>
        );
      } else if (match[3]) {
        // Bold: **text**
        parts.push(<strong key={`${lineIdx}-${match.index}`}>{match[3]}</strong>);
      }

      lastIndex = match.index + match[0].length;
    }

    // Remaining text
    if (lastIndex < cleanLine.length) {
      parts.push(cleanLine.slice(lastIndex));
    }

    if (isBullet) {
      return (
        <div key={lineIdx} className="chatbot-bullet">
          <span className="chatbot-bullet-dot">•</span>
          <span>{parts}</span>
        </div>
      );
    }

    return (
      <React.Fragment key={lineIdx}>
        {parts}
        {lineIdx < lines.length - 1 && <br />}
      </React.Fragment>
    );
  });
}

const THINKING_PHRASES = [
  'Thinking...',
  'Analyzing your question...',
  'Searching for information...',
  'Consulting our knowledge base...',
  'Gathering relevant data...',
  'Almost there...',
];

export const ChatBot = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: 'Hi! I\'m the Secure AI Office assistant. Ask me anything about devices, orders, quotes, designs, or portal navigation.' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [thinkingText, setThinkingText] = useState(THINKING_PHRASES[0]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (open && !minimized) {
      inputRef.current?.focus();
    }
  }, [open, minimized]);


  // Rotate thinking phrases while loading
  useEffect(() => {
    if (!loading) {
      setThinkingText(THINKING_PHRASES[0]);
      return;
    }
    let idx = 0;
    const interval = setInterval(() => {
      idx = (idx + 1) % THINKING_PHRASES.length;
      setThinkingText(THINKING_PHRASES[idx]);
    }, 3000);
    return () => clearInterval(interval);
  }, [loading]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading || !accessToken) return;

    const userMsg: ChatMessage = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const answer = await askChatbot(accessToken, text, messages);
      setMessages((prev) => [...prev, { role: 'assistant', content: answer }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Sorry, I couldn\'t process your request. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Floating button only
  if (!open) {
    return (
      <button
        className="chatbot-fab"
        onClick={() => setOpen(true)}
        aria-label="Open AI assistant"
        title="AI Assistant"
      >
        <Bot size={22} />
      </button>
    );
  }

  // Minimized state — small bar
  if (minimized) {
    return (
      <div className="chatbot-minimized" onClick={() => setMinimized(false)}>
        <Bot size={16} />
        <span>AI Assistant</span>
        <button
          className="chatbot-close-btn"
          onClick={(e) => { e.stopPropagation(); setOpen(false); setMinimized(false); }}
          aria-label="Close chat"
        >
          <X size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="chatbot-panel">
      {/* Header */}
      <div className="chatbot-header">
        <div className="chatbot-header-left">
          <Bot size={18} />
          <span>AI Assistant</span>
        </div>
        <div className="chatbot-header-actions">
          <button onClick={() => setMinimized(true)} aria-label="Minimize" title="Minimize">
            <Minimize2 size={14} />
          </button>
          <button onClick={() => { setOpen(false); setMinimized(false); }} aria-label="Close" title="Close">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="chatbot-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chatbot-msg chatbot-msg-${msg.role}`}>
            {msg.role === 'assistant' && (
              <span className="chatbot-avatar"><Bot size={14} /></span>
            )}
            <div className="chatbot-bubble">
              {msg.role === 'assistant'
                ? renderMarkdown(msg.content, navigate)
                : msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="chatbot-msg chatbot-msg-assistant">
            <span className="chatbot-avatar"><Bot size={14} /></span>
            <div className="chatbot-bubble chatbot-thinking">
              <div className="chatbot-thinking-dots">
                <span></span><span></span><span></span>
              </div>
              <span className="chatbot-thinking-text">{thinkingText}</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="chatbot-input-bar">
        <input
          ref={inputRef}
          type="text"
          placeholder="Ask about devices, orders, designs..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          className="chatbot-send-btn"
          onClick={handleSend}
          disabled={!input.trim() || loading}
          aria-label="Send message"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
};
