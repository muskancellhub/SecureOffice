import { api } from './client';

export interface IntakeChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface IntakeChatResponse {
  answer: string;
  extracted: Record<string, string | number>;
  is_complete: boolean;
}

export async function intakeChat(payload: {
  message: string;
  history: IntakeChatMessage[];
  current_fields: Record<string, unknown>;
}): Promise<IntakeChatResponse> {
  const { data } = await api.post<IntakeChatResponse>('/intake/chat', payload);
  return data;
}
