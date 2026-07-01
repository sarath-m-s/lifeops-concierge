import Constants from 'expo-constants';
import { AgentResponse, ConfirmResult, PendingAction, AuthStatus } from '../types/agent';

// In Expo Go, hostUri looks like "192.168.1.5:8081" — use the dev machine's LAN
// IP so a physical device can reach the backend. Falls back to localhost on
// web/simulator where hostUri is undefined.
const host = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
const BASE_URL = `http://${host}:8000`;

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
