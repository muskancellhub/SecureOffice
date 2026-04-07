import { api } from './client';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatRequest {
  message: string;
  history: ChatMessage[];
}

interface ChatResponse {
  answer: string;
}

const authHeaders = (accessToken: string) => ({ Authorization: `Bearer ${accessToken}` });

export const askChatbot = async (
  accessToken: string,
  message: string,
  history: ChatMessage[],
): Promise<string> => {
  const { data } = await api.post<ChatResponse>(
    '/chatbot/ask',
    { message, history } as ChatRequest,
    { headers: authHeaders(accessToken) },
  );
  return data.answer;
};
