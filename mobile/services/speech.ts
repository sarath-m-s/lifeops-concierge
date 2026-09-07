/**
 * Text-to-speech only. The app speaks its replies; it does not listen.
 *
 * There was a `mockTranscribe()` here that returned one hardcoded sentence after a
 * fake delay — the "voice-first" input was never real. Real speech-to-text needs a
 * native recognizer module, so input is text until that ships. TTS below is real.
 */
import * as Speech from 'expo-speech';

export const speech = {
  speak(text: string, onDone?: () => void) {
    Speech.stop();
    Speech.speak(text, { language: 'en-IN', pitch: 1.0, rate: 0.95, onDone });
  },

  stop() {
    Speech.stop();
  },

  isSpeaking(): Promise<boolean> {
    return Speech.isSpeakingAsync();
  },
};
