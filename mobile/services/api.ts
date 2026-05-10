import { AgentResponse, ConfirmResult, PendingAction, AuthStatus } from '../types/agent';

const BASE_URL = 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  sendMessage(message: string, sessionId?: string): Promise<AgentResponse> {
    return request<AgentResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  },

  confirmAction(action: PendingAction, sessionId: string = 'session_001'): Promise<ConfirmResult> {
    return request<ConfirmResult>('/confirm', {
      method: 'POST',
      body: JSON.stringify({ action, session_id: sessionId }),
    });
  },

  getAuthStatus(): Promise<AuthStatus> {
    return request<AuthStatus>('/auth/status');
  },
};
