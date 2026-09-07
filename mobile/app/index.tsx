import React, { useEffect, useRef } from 'react';
import { View, ScrollView, StyleSheet, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { ChatBubble } from '../components/ChatBubble';
import { ChatInput } from '../components/ChatInput';
import { StateView } from '../components/StateView';
import { usePlan } from '../state/PlanContext';
import { useChat } from '../hooks/useChat';
import { useAuth } from '../hooks/useAuth';
import { speech } from '../services/speech';
import { Icons } from '../constants/icons';
import { Colors, Radius, Spacing, Typography } from '../constants/theme';

const SUGGESTIONS = [
  'Book an Italian table for two on Friday at 8pm',
  'Order dessert to my place',
  'Restock coffee and milk',
];

export default function ChatScreen() {
  const router = useRouter();
  const { messages, loading, error, sendMessage } = useChat();
  const { status, connecting, connect } = useAuth();
  const { setPayload } = usePlan();
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(t);
  }, [messages.length]);

  const handleSend = async (text: string) => {
    const response = await sendMessage(text);
    if (!response) return;
    speech.speak(response.spoken_response);
    if (response.ui_payload.type === 'timeline' && response.ui_payload.items.length) {
      setPayload(response.ui_payload);
      setTimeout(() => router.push('/plan'), 450);
    }
  };

  if (status === 'checking') {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.brand} />
      </View>
    );
  }

  if (status === 'disconnected') {
    return (
      <StateView
        icon={Icons.connect}
        title="Connect your Swiggy account"
        body="Sign in with Swiggy to search restaurants, food, and groceries. You'll confirm every order before anything is placed."
        actionLabel="Connect Swiggy"
        onAction={connect}
        busy={connecting}
      />
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={styles.content}
        keyboardDismissMode="on-drag"
        showsVerticalScrollIndicator={false}
      >
        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}

        {messages.length === 1 && (
          <View style={styles.suggestions}>
            {SUGGESTIONS.map((s) => (
              <TouchableOpacity key={s} style={styles.chip} onPress={() => handleSend(s)} activeOpacity={0.8}>
                <Icons.spark size={14} color={Colors.brand} strokeWidth={2} />
                <Text style={styles.chipLabel}>{s}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {loading && (
          <View style={styles.thinking}>
            <ActivityIndicator size="small" color={Colors.brand} />
            <Text style={styles.thinkingLabel}>Checking with Swiggy…</Text>
          </View>
        )}

        {error && (
          <View style={styles.error}>
            <Icons.error size={16} color={Colors.error} strokeWidth={2} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
      </ScrollView>

      <ChatInput onSend={handleSend} loading={loading} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.background },
  scroll: { flex: 1 },
  content: { paddingTop: Spacing.lg, paddingBottom: Spacing.md },
  suggestions: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.sm, gap: Spacing.sm },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    borderRadius: Radius.full,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  chipLabel: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },
  thinking: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginHorizontal: Spacing.lg,
    marginTop: Spacing.sm,
  },
  thinkingLabel: { ...Typography.caption, color: Colors.textMuted },
  error: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginHorizontal: Spacing.lg,
    marginTop: Spacing.sm,
    padding: Spacing.md,
    borderRadius: Radius.md,
    backgroundColor: Colors.errorTint,
  },
  errorText: { ...Typography.caption, color: Colors.error, flex: 1 },
});
