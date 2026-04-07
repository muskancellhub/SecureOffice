import 'dotenv/config';
import express from 'express';
import cors from 'cors';

const app = express();
app.use(cors());
app.use(express.json());

const ANAM_API_KEY = process.env.ANAM_API_KEY;

if (!ANAM_API_KEY) {
  console.error('Missing ANAM_API_KEY in .env file');
  process.exit(1);
}

/**
 * Create a session token for the Anam AI persona.
 * The browser uses this short-lived token to stream the avatar via WebRTC.
 */
app.post('/api/session', async (_req, res) => {
  try {
    const response = await fetch('https://api.anam.ai/v1/auth/session-token', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${ANAM_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        personaConfig: {
          name: 'CellHub Assistant',
          avatarId: 'edf6fdcb-acab-44b8-b974-ded72665ee26', // Mia - studio
          voiceId: 'd79f2051-3a89-4fcc-8c71-cf5d53f9d9e0',  // Lauren - US Female
          llmId: '9d8900ee-257d-4401-8817-ba9c835e9d36',    // Gemini 2.5 Flash
          systemPrompt:
            "You are CellHub's friendly AI assistant. You help customers with mobile plans, billing, device troubleshooting, and general inquiries. Keep responses conversational, helpful, and concise. Speak naturally like a real customer service representative. If asked about plans, mention the Essentials plan at $29/mo and Premium Unlimited at $59/mo.",
        },
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error('Anam session error:', response.status, error);
      return res.status(response.status).json({ error });
    }

    const data = await response.json();
    res.json(data);
  } catch (err) {
    console.error('Session creation failed:', err);
    res.status(500).json({ error: 'Failed to create session' });
  }
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`[Server] Anam session server running on http://localhost:${PORT}`);
});
