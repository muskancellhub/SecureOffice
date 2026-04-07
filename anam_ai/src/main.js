import { createClient } from 'https://esm.sh/@anam-ai/js-sdk@latest';

/* ──────────────────── State ──────────────────── */

let anamClient = null;
let isConnected = false;
let isListening = false;
let currentTranscript = '';

/* ──────────────────── UI overlay ──────────────────── */

function createUI() {
  const container = document.createElement('div');
  container.id = 'speech-ui';
  container.innerHTML = `
    <style>
      #speech-ui {
        position: fixed; bottom: 0; left: 0; right: 0;
        display: flex; flex-direction: column; align-items: center;
        pointer-events: none; z-index: 100;
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      }
      #speech-bubble {
        background: rgba(255,255,255,0.95);
        color: #1a1a2e;
        padding: 16px 24px;
        border-radius: 20px;
        max-width: 550px;
        margin-bottom: 16px;
        font-size: 15px;
        line-height: 1.5;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        opacity: 0;
        transform: translateY(10px) scale(0.95);
        transition: opacity 0.3s ease, transform 0.3s ease;
        position: relative;
        text-align: center;
      }
      #speech-bubble.visible {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
      #speech-bubble::after {
        content: '';
        position: absolute;
        bottom: -8px;
        left: 50%;
        transform: translateX(-50%);
        width: 0; height: 0;
        border-left: 8px solid transparent;
        border-right: 8px solid transparent;
        border-top: 8px solid rgba(255,255,255,0.95);
      }
      #user-bubble {
        background: rgba(99,102,241,0.2);
        color: rgba(255,255,255,0.9);
        padding: 10px 18px;
        border-radius: 16px;
        max-width: 450px;
        margin-bottom: 8px;
        font-size: 13px;
        line-height: 1.4;
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        opacity: 0;
        transform: translateY(10px) scale(0.95);
        transition: opacity 0.3s ease, transform 0.3s ease;
        text-align: center;
        font-style: italic;
      }
      #user-bubble.visible {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
      #controls-bar {
        display: flex; gap: 12px;
        margin-bottom: 28px;
        pointer-events: all;
        flex-wrap: wrap;
        justify-content: center;
        align-items: center;
      }
      .speech-btn {
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        color: white;
        border: none;
        padding: 12px 20px;
        border-radius: 12px;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 4px 16px rgba(99,102,241,0.3);
      }
      .speech-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 24px rgba(99,102,241,0.5);
      }
      .speech-btn:active { transform: scale(0.97); }
      .speech-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
        transform: none !important;
      }
      .speech-btn.secondary {
        background: rgba(255,255,255,0.1);
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
      }
      #btn-mic {
        width: 64px; height: 64px;
        border-radius: 50%;
        padding: 0;
        display: flex; align-items: center; justify-content: center;
        font-size: 24px;
        position: relative;
      }
      #btn-mic.listening {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        box-shadow: 0 0 0 0 rgba(239,68,68,0.5);
        animation: mic-pulse 1.5s ease-in-out infinite;
      }
      @keyframes mic-pulse {
        0% { box-shadow: 0 0 0 0 rgba(239,68,68,0.5); }
        70% { box-shadow: 0 0 0 15px rgba(239,68,68,0); }
        100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); }
      }
      #status-text {
        color: rgba(255,255,255,0.5);
        font-size: 12px;
        margin-bottom: 8px;
        text-align: center;
        min-height: 18px;
      }
      .speaking-indicator {
        display: inline-block;
        width: 8px; height: 8px;
        background: #10b981;
        border-radius: 50%;
        margin-right: 8px;
        animation: pulse 0.6s ease-in-out infinite alternate;
      }
      @keyframes pulse {
        from { opacity: 0.4; transform: scale(0.8); }
        to   { opacity: 1;   transform: scale(1.2); }
      }
      #input-row {
        display: flex; gap: 8px;
        margin-bottom: 12px;
        pointer-events: all;
      }
      #custom-input {
        background: rgba(255,255,255,0.1);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.2);
        color: white;
        padding: 12px 16px;
        border-radius: 12px;
        font-size: 14px;
        width: 280px;
        outline: none;
        pointer-events: all;
        transition: border-color 0.2s;
      }
      #custom-input::placeholder { color: rgba(255,255,255,0.4); }
      #custom-input:focus { border-color: #6366f1; }
    </style>

    <div id="user-bubble"></div>
    <div id="speech-bubble"></div>
    <div id="status-text"></div>

    <div id="input-row">
      <input id="custom-input" type="text" placeholder="Type a message or use the mic..." />
      <button class="speech-btn" id="btn-send">Send</button>
    </div>

    <div id="controls-bar">
      <button class="speech-btn secondary" id="btn-connect">Connect</button>
      <button class="speech-btn" id="btn-mic" disabled>🎤</button>
      <button class="speech-btn secondary" id="btn-disconnect" disabled>Disconnect</button>
    </div>
  `;
  document.body.appendChild(container);

  document.getElementById('btn-connect').addEventListener('click', connectAnam);
  document.getElementById('btn-mic').addEventListener('click', toggleMic);
  document.getElementById('btn-disconnect').addEventListener('click', disconnectAnam);
  document.getElementById('btn-send').addEventListener('click', sendTextMessage);
  document.getElementById('custom-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendTextMessage();
  });
}

function setStatus(text) {
  document.getElementById('status-text').textContent = text;
}

function showBubble(text) {
  const bubble = document.getElementById('speech-bubble');
  bubble.innerHTML = `<span class="speaking-indicator"></span>${text}`;
  bubble.classList.add('visible');
}

function hideBubble() {
  document.getElementById('speech-bubble').classList.remove('visible');
}

function showUserBubble(text) {
  const bubble = document.getElementById('user-bubble');
  bubble.textContent = `You: ${text}`;
  bubble.classList.add('visible');
}

function hideUserBubble() {
  document.getElementById('user-bubble').classList.remove('visible');
}

/* ──────────────────── Anam AI Connection ──────────────────── */

async function connectAnam() {
  if (isConnected) return;
  setStatus('Connecting to Anam AI...');

  try {
    // Get session token from our backend
    const tokenRes = await fetch('/api/session', { method: 'POST' });
    if (!tokenRes.ok) {
      const err = await tokenRes.text();
      throw new Error(`Token request failed: ${err}`);
    }
    const session = await tokenRes.json();
    const sessionToken = session.sessionToken;
    if (!sessionToken) throw new Error('No session token in response');

    // Create Anam client and stream to video element
    anamClient = createClient(sessionToken);

    // Listen to Anam events
    anamClient.addListener('MESSAGE_STREAM_EVENT_RECEIVED', (event) => {
      if (event.role === 'assistant') {
        currentTranscript += event.content;
        showBubble(currentTranscript);
      }
    });

    anamClient.addListener('MESSAGE_HISTORY_UPDATED', (messages) => {
      if (messages.length > 0) {
        const last = messages[messages.length - 1];
        if (last.role === 'assistant') {
          currentTranscript = last.content;
          showBubble(currentTranscript);
          setTimeout(hideBubble, 4000);
          currentTranscript = '';
        } else if (last.role === 'user') {
          showUserBubble(last.content);
        }
      }
    });

    anamClient.addListener('CONNECTION_ESTABLISHED', () => {
      console.log('[Anam] Connection established');
      isConnected = true;
      isListening = true;
      setStatus('Connected — speaking to the avatar');
      document.getElementById('btn-connect').disabled = true;
      document.getElementById('btn-mic').disabled = false;
      document.getElementById('btn-mic').classList.add('listening');
      document.getElementById('btn-mic').textContent = '⏹';
      document.getElementById('btn-disconnect').disabled = false;
    });

    anamClient.addListener('CONNECTION_CLOSED', () => {
      console.log('[Anam] Connection closed');
      cleanupState();
    });

    anamClient.addListener('ERROR', (error) => {
      console.error('[Anam] Error:', error);
      setStatus(`Error: ${error.message || 'Unknown error'}`);
    });

    await anamClient.streamToVideoElement('persona-video');
  } catch (err) {
    console.error('[Anam] Connection failed:', err);
    setStatus(`Connection failed: ${err.message}`);
    cleanupState();
  }
}

function toggleMic() {
  if (!anamClient || !isConnected) return;

  if (isListening) {
    anamClient.muteInputAudio();
    isListening = false;
    document.getElementById('btn-mic').classList.remove('listening');
    document.getElementById('btn-mic').textContent = '🎤';
    setStatus('Mic muted — click to talk');
  } else {
    anamClient.unmuteInputAudio();
    isListening = true;
    document.getElementById('btn-mic').classList.add('listening');
    document.getElementById('btn-mic').textContent = '⏹';
    setStatus('Listening... speak now');
  }
}

function sendTextMessage() {
  const input = document.getElementById('custom-input');
  const text = input.value.trim();
  if (!text || !anamClient || !isConnected) return;

  showUserBubble(text);
  input.value = '';

  anamClient.sendMessage(text);
}

function disconnectAnam() {
  if (anamClient) {
    anamClient.stopStreaming();
    anamClient = null;
  }
  cleanupState();
}

function cleanupState() {
  isConnected = false;
  isListening = false;
  currentTranscript = '';
  anamClient = null;

  setStatus('Disconnected');
  hideBubble();
  hideUserBubble();

  document.getElementById('btn-connect').disabled = false;
  document.getElementById('btn-mic').disabled = true;
  document.getElementById('btn-mic').classList.remove('listening');
  document.getElementById('btn-mic').textContent = '🎤';
  document.getElementById('btn-disconnect').disabled = true;
}

/* ──────────────────── Cleanup on page unload ──────────────────── */

window.addEventListener('beforeunload', () => {
  if (anamClient) {
    anamClient.stopStreaming();
  }
});

/* ──────────────────── Init ──────────────────── */

createUI();
setStatus('Click "Connect" to start a conversation');
