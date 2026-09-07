import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { ConfirmResult, PendingAction, AuthStatus } from '../types/agent';

export interface LiveKitToken {
  room_name: string;
  token: string;
  url: string;
}

// Point at the deployed backend with EXPO_PUBLIC_API_URL (e.g. in eas.json or .env):
//   EXPO_PUBLIC_API_URL=https://lifeops-concierge.onrender.com
// Without it we fall back to the dev machine over LAN, which is local-only — in Expo Go
// hostUri looks like "192.168.1.5:8081", so a physical device can still reach uvicorn.
const lanHost = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
const BASE_URL = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') ?? `http://${lanHost}:8000`;

const SESSION_KEY = 'lifeops.session_id';
let sessionId: string | null = null;

export interface LoginInfo {
  session_id: string;
  authorize_url: string | null;
}

async function login(): Promise<LoginInfo> {
  const res = await fetch(`${BASE_URL}/auth/login`, { method: 'POST' });
  if (!res.ok) throw new Error(`Login failed (${res.status}): ${await res.text()}`);
  const info: LoginInfo = await res.json();
  sessionId = info.session_id;
  await AsyncStorage.setItem(SESSION_KEY, info.session_id);
  return info;
}

async function currentSession(): Promise<string> {
  if (sessionId) return sessionId;
  const stored = await AsyncStorage.getItem(SESSION_KEY);
  if (stored) {
    sessionId = stored;
    return stored;
  }
  return (await login()).session_id;
}

async function clearSession() {
  sessionId = null;
  await AsyncStorage.removeItem(SESSION_KEY);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const id = await currentSession();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Session-Id': id, ...(options?.headers ?? {}) },
  });
  if (res.status === 401) {
    // The Swiggy access token lives 5 days and there is no refresh grant in v1, so an
    // expired session means re-running the whole authorization flow, not a token swap.
    await clearSession();
    throw new Error('Swiggy session expired. Connect again from Settings.');
  }
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  login,
  clearSession,

  /** Start a fresh connect. Returns the URL to open in a browser (null in mock mode). */
  async connect(): Promise<LoginInfo> {
    await clearSession();
    return login();
  },

  getLiveKitToken(): Promise<LiveKitToken> {
    return request<LiveKitToken>('/livekit/token', { method: 'POST' });
  },

  resetConversation(): Promise<{ status: string }> {
    return request<{ status: string }>('/chat/reset', { method: 'POST' });
  },

  confirmAction(action: PendingAction): Promise<ConfirmResult> {
    return request<ConfirmResult>('/confirm', {
      method: 'POST',
      body: JSON.stringify({ action, session_id: sessionId ?? '' }),
    });
  },

  async logout(): Promise<void> {
    const id = await currentSession();
    await fetch(`${BASE_URL}/auth/logout`, {
      method: 'POST',
      headers: { 'X-Session-Id': id },
    }).catch(() => undefined);
    await clearSession();
  },

  async getAuthStatus(): Promise<AuthStatus> {
    const id = await currentSession();
    const res = await fetch(`${BASE_URL}/auth/status?session_id=${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },
};
