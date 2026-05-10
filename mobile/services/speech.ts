import * as Speech from 'expo-speech';

const DEMO_TRANSCRIPT =
  'Plan Friday evening for two. Italian dinner around 8 PM, dessert later at home, and restock coffee for tomorrow.';

export const speech = {
  speak(text: string, onDone?: () => void) {
    Speech.stop();
    Speech.speak(text, {
      language: 'en-IN',
      pitch: 1.0,
      rate: 0.95,
      onDone,
    });
  },

  stop() {
    Speech.stop();
  },

  async isSpeaking(): Promise<boolean> {
    return Speech.isSpeakingAsync();
  },

  /** Phase 2 mock: returns the hero demo transcript after a short simulated delay. */
  async mockTranscribe(): Promise<string> {
    await new Promise((r) => setTimeout(r, 1500));
    return DEMO_TRANSCRIPT;
  },
};
