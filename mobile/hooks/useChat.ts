import { useCallback, useState } from 'react';
import { ChatMessage, AgentResponse } from '../types/agent';
import { api } from '../services/api';

function makeId() {
  return Math.random().toString(36).slice(2);
}

const WELCOME: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  text: "I can book a table, order food, or restock groceries — or plan all three at once. What's the plan?",
  timestamp: new Date(),
};

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (text: string): Promise<AgentResponse | null> => {
    setMessages((prev) => [...prev, { id: makeId(), role: 'user', text, timestamp: new Date() }]);
    setLoading(true);
    setError(null);

    try {
      const response = await api.sendMessage(text);
      setMessages((prev) => [
        ...prev,
        {
          id: makeId(),
          role: 'assistant',
          text: response.spoken_response,
          timestamp: new Date(),
          payload: response.ui_payload,
        },
      ]);
      return response;
    } catch (e: any) {
      setError(e?.message ?? 'Something went wrong.');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { messages, loading, error, sendMessage };
}
