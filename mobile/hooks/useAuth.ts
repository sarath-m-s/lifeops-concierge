import { useCallback, useEffect, useState } from 'react';
import { AppState, Linking } from 'react-native';
import { api } from '../services/api';

type Status = 'checking' | 'connected' | 'disconnected';

/**
 * Swiggy connection state. The OAuth flow finishes in a browser and deep-links
 * back, so the status is re-checked whenever the app returns to the foreground.
 */
export function useAuth() {
  const [status, setStatus] = useState<Status>('checking');
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const info = await api.getAuthStatus();
      setStatus(info.authenticated ? 'connected' : 'disconnected');
    } catch {
      setStatus('disconnected');
    }
  }, []);

  useEffect(() => {
    refresh();
    const sub = AppState.addEventListener('change', (s) => {
      if (s === 'active') refresh();
    });
    return () => sub.remove();
  }, [refresh]);

  const connect = useCallback(async () => {
    setConnecting(true);
    setError(null);
    try {
      const info = await api.connect();
      if (info.authorize_url) {
        // Phone and OTP are entered on Swiggy's own consent page, never in this app.
        await Linking.openURL(info.authorize_url);
      }
      await refresh();
    } catch (e: any) {
      setError(e?.message ?? 'Could not start the Swiggy login.');
    } finally {
      setConnecting(false);
    }
  }, [refresh]);

  const disconnect = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setStatus('disconnected');
    }
  }, []);

  return { status, connecting, error, connect, disconnect, refresh };
}
