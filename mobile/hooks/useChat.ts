import { useState, useCallback } from 'react';
import { ChatMessage, AgentResponse, UIPayload } from '../types/agent';
import { api } from '../services/api';

function makeId() {
  return Math.random().toString(36).slice(2);
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: 'Hi! I can plan your evening across Swiggy Food, Instamart, and Dineout. Try: "Plan Friday evening for two."',
      timestamp: new Date(),
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [lastPayload, setLastPayload] = useState<UIPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (text: string): Promise<AgentResponse | null> => {
    const userMsg: ChatMessage = {
      id: makeId(),
      role: 'user',
      text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setError(null);

    try {
      const response = await api.sendMessage(text);
      const assistantMsg: ChatMessage = {
        id: makeId(),
        role: 'assistant',
        text: response.spoken_response,
        timestamp: new Date(),
        spoken: true,
        payload: response.ui_payload,
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setLastPayload(response.ui_payload);
      return response;
    } catch (e: any) {
      setError(e.message ?? 'Something went wrong.');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { messages, loading, error, lastPayload, sendMessage };
}
