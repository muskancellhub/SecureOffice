/**
 * AnamAvatar — AI avatar widget for the Business Intake form.
 *
 * Architecture:
 * - Anam AI handles VOICE conversation only (no structured output)
 * - Backend /anam/parse-intent (GPT-4.1-mini) handles ALL form filling
 * - Every user message is sent to the backend agent to extract field updates
 *
 * Supports two modes:
 * - Floating widget (default) — bottom-left on BusinessIntakePage
 * - Embedded mode (embedded=true) — inline panel inside BusinessIntakeModal
 */

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface AnamAvatarProps {
  formState: Record<string, string>;
  onFormUpdate: (updates: Record<string, string>) => void;
  /** Render inline (no floating wrapper, no minimize, no header) */
  embedded?: boolean;
  /** Custom video element ID to avoid conflicts when multiple instances exist */
  videoId?: string;
}

export interface AnamAvatarHandle {
  disconnect: () => void;
}

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export const AnamAvatar = forwardRef<AnamAvatarHandle, AnamAvatarProps>(({ formState, onFormUpdate, embedded = false, videoId }, ref) => {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [isListening, setIsListening] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [currentTranscript, setCurrentTranscript] = useState('');
  const [statusText, setStatusText] = useState('Click to start your AI assistant');
  const [fieldsJustUpdated, setFieldsJustUpdated] = useState<string[]>([]);

  const videoRef = useRef<HTMLVideoElement>(null);
  const anamClientRef = useRef<any>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const formStateRef = useRef(formState);

  // Track which history messages we already processed to avoid duplicates
  const processedHistoryLenRef = useRef(0);
  // Debounce timer for finalizing assistant messages
  const streamDoneTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Accumulate the full streaming transcript across chunks
  const streamingTranscriptRef = useRef('');
  // Flag: are we currently in an assistant stream?
  const isStreamingRef = useRef(false);

  useEffect(() => {
    formStateRef.current = formState;
  }, [formState]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentTranscript]);

  useEffect(() => {
    if (fieldsJustUpdated.length > 0) {
      const t = setTimeout(() => setFieldsJustUpdated([]), 3500);
      return () => clearTimeout(t);
    }
  }, [fieldsJustUpdated]);

  /** Send transcript to backend agent for form field extraction */
  const parseIntentViaBackend = useCallback(
    async (transcript: string) => {
      if (!transcript || transcript.trim().length < 3) return;
      try {
        const resp = await fetch(`${API_BASE}/anam/parse-intent`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            transcript,
            current_form_state: formStateRef.current,
          }),
        });
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.updates && Object.keys(data.updates).length > 0) {
          console.log('[AnamAvatar] Form update:', data.updates);
          onFormUpdate(data.updates);
          setFieldsJustUpdated(Object.keys(data.updates));
        }
      } catch (e) {
        console.warn('[AnamAvatar] parse-intent failed:', e);
      }
    },
    [onFormUpdate],
  );

  /**
   * Finalize the current assistant streaming message.
   * Called after a debounce when no new stream chunks arrive.
   */
  const finalizeAssistantMessage = useCallback(() => {
    const text = streamingTranscriptRef.current.trim();
    if (text) {
      setMessages((prev) => [...prev, { role: 'assistant', content: text }]);
      // NOTE: Do NOT parse assistant messages — they cause wrong field updates
      // because the assistant says things like "do you need 10 cameras?" and the
      // agent interprets that as the user wanting 10 cameras.
    }
    streamingTranscriptRef.current = '';
    isStreamingRef.current = false;
    setCurrentTranscript('');
  }, [parseIntentViaBackend]);

  /** Connect to Anam AI avatar */
  const connect = useCallback(async () => {
    if (status === 'connected' || status === 'connecting') return;
    setStatus('connecting');
    setStatusText('Connecting to AI assistant...');

    try {
      const tokenResp = await fetch(`${API_BASE}/anam/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ form_state: formStateRef.current }),
      });

      if (!tokenResp.ok) {
        throw new Error(`Session request failed: ${tokenResp.status}`);
      }

      const session = await tokenResp.json();
      const sessionToken = session.sessionToken;
      if (!sessionToken) throw new Error('No session token received');

      // @ts-ignore — external CDN module
      const { createClient } = await import(/* @vite-ignore */ 'https://esm.sh/@anam-ai/js-sdk@latest');

      const client = createClient(sessionToken);
      anamClientRef.current = client;

      // ── Stream events: accumulate transcript with debounce ──
      client.addListener('MESSAGE_STREAM_EVENT_RECEIVED', (event: any) => {
        if (event.role === 'assistant') {
          isStreamingRef.current = true;
          streamingTranscriptRef.current += event.content;
          setCurrentTranscript(streamingTranscriptRef.current);

          // Reset the debounce timer — finalize only after 1.5s of silence
          if (streamDoneTimerRef.current) {
            clearTimeout(streamDoneTimerRef.current);
          }
          streamDoneTimerRef.current = setTimeout(() => {
            finalizeAssistantMessage();
          }, 1500);
        }
      });

      // ── History updates: only process USER messages (assistant handled by stream) ──
      client.addListener('MESSAGE_HISTORY_UPDATED', (msgs: any[]) => {
        // Process only messages we haven't seen yet
        const startIdx = processedHistoryLenRef.current;
        processedHistoryLenRef.current = msgs.length;

        for (let i = startIdx; i < msgs.length; i++) {
          const msg = msgs[i];
          if (msg.role === 'user') {
            setMessages((prev) => {
              // Avoid duplicate if we already added it from sendMessage()
              const lastMsg = prev[prev.length - 1];
              if (lastMsg?.role === 'user' && lastMsg.content === msg.content) {
                return prev;
              }
              return [...prev, { role: 'user', content: msg.content }];
            });
            parseIntentViaBackend(msg.content);
          }
          // For assistant messages from history: if we're not currently streaming,
          // this is a completed message we might have missed
          if (msg.role === 'assistant' && !isStreamingRef.current && i >= startIdx) {
            setMessages((prev) => {
              const lastMsg = prev[prev.length - 1];
              if (lastMsg?.role === 'assistant' && lastMsg.content === msg.content) {
                return prev;
              }
              return [...prev, { role: 'assistant', content: msg.content }];
            });
          }
        }
      });

      client.addListener('CONNECTION_ESTABLISHED', () => {
        setStatus('connected');
        setIsListening(true);
        setStatusText('Connected — speak or type');
        processedHistoryLenRef.current = 0;
      });

      client.addListener('CONNECTION_CLOSED', () => {
        cleanup();
      });

      client.addListener('ERROR', (error: any) => {
        console.error('[AnamAvatar] Error:', error);
        setStatusText(`Error: ${error?.message || 'Unknown'}`);
      });

      const vid = videoRef.current;
      if (vid) {
        await client.streamToVideoElement(vid.id);
      }
    } catch (err: any) {
      console.error('[AnamAvatar] Connection failed:', err);
      setStatusText(`Failed: ${err.message}`);
      setStatus('disconnected');
    }
  }, [status, parseIntentViaBackend, finalizeAssistantMessage]);

  const disconnect = useCallback(() => {
    if (streamDoneTimerRef.current) clearTimeout(streamDoneTimerRef.current);
    if (anamClientRef.current) {
      anamClientRef.current.stopStreaming();
    }
    cleanup();
  }, []);

  // Expose disconnect for parent components (used by modal on close)
  useImperativeHandle(ref, () => ({ disconnect }), [disconnect]);

  const cleanup = () => {
    anamClientRef.current = null;
    setStatus('disconnected');
    setIsListening(false);
    setCurrentTranscript('');
    streamingTranscriptRef.current = '';
    isStreamingRef.current = false;
    processedHistoryLenRef.current = 0;
    setStatusText('Disconnected — click to reconnect');
  };

  const toggleMic = useCallback(() => {
    const client = anamClientRef.current;
    if (!client || status !== 'connected') return;

    if (isListening) {
      client.muteInputAudio();
      setIsListening(false);
      setStatusText('Mic muted — click mic to talk');
    } else {
      client.unmuteInputAudio();
      setIsListening(true);
      setStatusText('Listening... speak now');
    }
  }, [status, isListening]);

  const sendMessage = useCallback(() => {
    const text = inputText.trim();
    if (!text || !anamClientRef.current || status !== 'connected') return;

    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    anamClientRef.current.sendMessage(text);
    parseIntentViaBackend(text);
    setInputText('');
  }, [inputText, status, parseIntentViaBackend]);

  useEffect(() => {
    return () => {
      if (streamDoneTimerRef.current) clearTimeout(streamDoneTimerRef.current);
      if (anamClientRef.current) anamClientRef.current.stopStreaming();
    };
  }, []);

  const actualVideoId = videoId || 'anam-persona-video';

  /* ── Shared inner markup (video + chat + input) ── */
  const innerContent = (
    <>
      {/* Video */}
      <div className="anam-avatar-video-container">
        <video
          id={actualVideoId}
          ref={videoRef}
          autoPlay
          playsInline
          muted={false}
          className="anam-avatar-video"
        />
        {status !== 'connected' && (
          <div className="anam-avatar-video-overlay">
            <button
              className="anam-connect-btn"
              onClick={connect}
              disabled={status === 'connecting'}
            >
              {status === 'connecting' ? (
                <span className="anam-spinner" />
              ) : (
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5,3 19,12 5,21" />
                </svg>
              )}
            </button>
            <span className="anam-overlay-text">
              {status === 'connecting' ? 'Connecting...' : 'Start AI Assistant'}
            </span>
          </div>
        )}
      </div>

      {/* Field update indicator */}
      {fieldsJustUpdated.length > 0 && (
        <div className="anam-field-update-banner">
          Updated: {fieldsJustUpdated.join(', ')}
        </div>
      )}

      {/* Chat */}
      <div className="anam-avatar-chat">
        {messages.length === 0 && !currentTranscript && (
          <div className="anam-chat-empty">
            Click the play button above to start. I'll help you fill out the form!
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`anam-chat-msg ${msg.role}`}>
            <span className="anam-chat-role">{msg.role === 'user' ? 'You' : 'AI'}</span>
            <span className="anam-chat-text">{msg.content}</span>
          </div>
        ))}
        {currentTranscript && (
          <div className="anam-chat-msg assistant streaming">
            <span className="anam-chat-role">AI</span>
            <span className="anam-chat-text">{currentTranscript}</span>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Status */}
      <div className="anam-avatar-status">{statusText}</div>

      {/* Input */}
      <div className="anam-avatar-input-area">
        <input
          type="text"
          className="anam-avatar-input"
          placeholder={status === 'connected' ? 'Type a message...' : 'Connect first...'}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          disabled={status !== 'connected'}
        />
        <button
          className={`anam-mic-btn ${isListening ? 'listening' : ''}`}
          onClick={toggleMic}
          disabled={status !== 'connected'}
          title={isListening ? 'Mute mic' : 'Unmute mic'}
        >
          {isListening ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <rect x="9" y="2" width="6" height="12" rx="3" />
              <path d="M5 10a7 7 0 0 0 14 0" fill="none" stroke="currentColor" strokeWidth="2" />
              <line x1="12" y1="17" x2="12" y2="21" stroke="currentColor" strokeWidth="2" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="2" width="6" height="12" rx="3" />
              <path d="M5 10a7 7 0 0 0 14 0" />
              <line x1="12" y1="17" x2="12" y2="21" />
              <line x1="2" y1="2" x2="22" y2="22" stroke="red" strokeWidth="2" />
            </svg>
          )}
        </button>
        {status === 'connected' && (
          <button className="anam-disconnect-btn" onClick={disconnect} title="Disconnect">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
      </div>
    </>
  );

  /* ── Embedded mode: no floating wrapper, no minimize, no header ── */
  if (embedded) {
    return <div className="anam-avatar-embedded">{innerContent}</div>;
  }

  /* ── Floating widget mode (original) ── */

  // Minimized bubble
  if (isMinimized) {
    return (
      <button
        className="anam-avatar-minimized"
        onClick={() => setIsMinimized(false)}
        title="Open AI Assistant"
      >
        <div className="anam-avatar-mini-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        {status === 'connected' && <span className="anam-avatar-mini-dot" />}
      </button>
    );
  }

  return (
    <div className="anam-avatar-widget">
      {/* Header */}
      <div className="anam-avatar-header">
        <div className="anam-avatar-header-left">
          <span className={`anam-status-dot ${status}`} />
          <span className="anam-avatar-title">AI Assistant</span>
        </div>
        <div className="anam-avatar-header-actions">
          <button className="anam-header-btn" onClick={() => setIsMinimized(true)} title="Minimize">
            &mdash;
          </button>
        </div>
      </div>
      {innerContent}
    </div>
  );
});
