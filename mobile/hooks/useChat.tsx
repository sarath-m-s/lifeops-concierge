import { useCallback, useState } from 'react';
import { AgentTurn, ChatMessage } from '../types/agent';
import { api } from '../services/api';

const id = () => Math.random().toString(36).slice(2);

/** Never render an empty error. `??` only guards null/undefined, so a blank
 *  message string used to produce a red box with no text in it. */
function describeError(e: unknown): string {
  const raw = e instanceof Error ? e.message : typeof e === 'string' ? e : '';
  const text = raw.trim();
  if (!text) return "That didn't go through. Try again?";
  if (/network request failed|failed to fetch/i.test(text)) {
    return "Can't reach the server. Is the backend running?";
  }
  return text;
}

const WELCOME: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  text: "I can book a table, order food, or restock groceries. Ask me anything — I'll keep the thread as we go.",
  timestamp: new Date(),
};

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [loading, setLoading] = useState(false);

  const sendMessage = useCallback(async (text: string): Promise<AgentTurn | null> => {
    setMessages((prev) => [...prev, { id: id(), role: 'user', text, timestamp: new Date() }]);
    setLoading(true);
    try {
      const turn = await api.sendMessage(text);
      setMessages((prev) => [
        ...prev,
        { id: id(), role: 'assistant', text: turn.say, timestamp: new Date(), components: turn.components },
      ]);
      return turn;
    } catch (e: any) {
      // A failure has to appear in the transcript. Putting it in a separate error
      // slot meant the next message cleared it, and the user was left looking at
      // a question with no answer and no explanation.
      setMessages((prev) => [
        ...prev,
        {
          id: id(),
          role: 'assistant',
          text: describeError(e),
          timestamp: new Date(),
          failed: true,
        },
      ]);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(async () => {
    await api.resetConversation().catch(() => undefined);
    setMessages([WELCOME]);
  }, []);

  return { messages, loading, sendMessage, reset };
}
