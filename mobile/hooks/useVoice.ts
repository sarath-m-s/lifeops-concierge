import { useState, useCallback } from 'react';
import { speech } from '../services/speech';

type VoiceState = 'idle' | 'listening' | 'processing';

export function useVoice(onTranscript: (text: string) => void) {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');

  const startListening = useCallback(async () => {
    if (voiceState !== 'idle') return;
    setVoiceState('listening');
    await new Promise((r) => setTimeout(r, 800)); // simulate mic open
    setVoiceState('processing');
    try {
      const transcript = await speech.mockTranscribe();
      onTranscript(transcript);
    } finally {
      setVoiceState('idle');
    }
  }, [voiceState, onTranscript]);

  const stopListening = useCallback(() => {
    setVoiceState('idle');
  }, []);

  return { voiceState, startListening, stopListening };
}
