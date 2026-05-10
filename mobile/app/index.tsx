import React, { useRef, useEffect } from 'react';
import { View, ScrollView, StyleSheet, Text, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { setPlanPayload } from './plan';
import { ChatBubble } from '../components/ChatBubble';
import { ChatInput } from '../components/ChatInput';
import { useChat } from '../hooks/useChat';
import { speech } from '../services/speech';
import { Colors, Spacing, Typography } from '../constants/theme';

export default function ChatScreen() {
  const router = useRouter();
  const { messages, loading, error, sendMessage } = useChat();
  const scrollRef = useRef<ScrollView>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
  }, [messages.length]);

  const handleSend = async (text: string) => {
    const response = await sendMessage(text);
    if (!response) return;

    // Speak the response
    speech.speak(response.spoken_response);

    // Navigate to Plan tab if we got a timeline, wiring up the real payload
    if (response.ui_payload.type === 'timeline') {
      setPlanPayload(response.ui_payload);
      setTimeout(() => router.push('/plan'), 600);
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardDismissMode="on-drag"
        showsVerticalScrollIndicator={false}
      >
        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}

        {loading && (
          <View style={styles.loadingRow}>
            <ActivityIndicator size="small" color={Colors.swiggyOrange} />
            <Text style={styles.loadingText}>Thinking…</Text>
          </View>
        )}

        {error && (
          <View style={styles.errorRow}>
            <Text style={styles.errorText}>⚠️ {error}</Text>
          </View>
        )}
      </ScrollView>

      <ChatInput onSend={handleSend} loading={loading} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  scroll: { flex: 1 },
  scrollContent: { paddingTop: Spacing.lg, paddingBottom: Spacing.md },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: Spacing.lg,
    marginVertical: Spacing.sm,
    gap: Spacing.sm,
  },
  loadingText: { fontSize: Typography.fontSizeSm, color: Colors.textMuted },
  errorRow: {
    marginHorizontal: Spacing.lg,
    marginVertical: Spacing.sm,
    backgroundColor: '#FFF0F0',
    padding: Spacing.sm,
    borderRadius: 8,
  },
  errorText: { fontSize: Typography.fontSizeSm, color: Colors.error },
});
