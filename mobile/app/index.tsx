import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, ScrollView, StyleSheet, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { ChatBubble } from '../components/ChatBubble';
import { ChatInput } from '../components/ChatInput';
import { Renderer } from '../components/Renderer';
import { StateView } from '../components/StateView';
import { usePlan } from '../state/PlanContext';
import { useChat } from '../hooks/useChat';
import { useAuth } from '../hooks/useAuth';
import { api } from '../services/api';
import { speech } from '../services/speech';
import { PendingAction } from '../types/agent';
import { Icons } from '../constants/icons';
import { Colors, Radius, Spacing, Typography } from '../constants/theme';

const OPENERS = [
  'What can I order near me?',
  'Any coffee deals on Instamart?',
  'Book a table for two this Friday',
];

export default function ChatScreen() {
  const { messages, loading, sendMessage, reset } = useChat();
  const { status, connecting, connect } = useAuth();
  const { record, settle, results } = usePlan();
  const [confirming, setConfirming] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 90);
    return () => clearTimeout(t);
  }, [messages.length]);

  const handleSend = useCallback(async (text: string) => {
    const turn = await sendMessage(text);
    if (turn?.say) speech.speak(turn.say);
  }, [sendMessage]);

  const handleConfirm = useCallback(async (action: PendingAction, title: string, total: string) => {
    record(action, title, total);
    setConfirming(action.display_summary);
    try {
      const res = await api.confirmAction(action);
      settle(action.display_summary, res.success, res.message);
      speech.speak(res.message);
    } catch (e: any) {
      settle(action.display_summary, false, String(e?.message || '').trim() || 'Could not place that.');
    } finally {
      setConfirming(null);
    }
  }, [record, settle]);

  if (status === 'checking') {
    return <View style={styles.center}><ActivityIndicator color={Colors.brand} /></View>;
  }

  if (status === 'disconnected') {
    return (
      <StateView
        icon={Icons.connect}
        title="Connect your Swiggy account"
        body="Sign in with Swiggy to search restaurants, food, and groceries. Nothing is ordered without you tapping Confirm."
        actionLabel="Connect Swiggy"
        onAction={connect}
        busy={connecting}
      />
    );
  }

  const ctx = {
    onSuggest: handleSend,
    onConfirm: handleConfirm,
    confirmingId: confirming,
    resultFor: (summary: string) => results[summary],
  };

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
          <View key={msg.id} style={styles.turn}>
            <ChatBubble message={msg} />
            <Renderer components={msg.components} ctx={ctx} />
          </View>
        ))}

        {messages.length === 1 && (
          <View style={styles.openers}>
            {OPENERS.map((s) => (
              <TouchableOpacity key={s} style={styles.opener} onPress={() => handleSend(s)} activeOpacity={0.8}>
                <Icons.spark size={14} color={Colors.brand} strokeWidth={2} />
                <Text style={styles.openerText}>{s}</Text>
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
      </ScrollView>

      {messages.length > 1 && (
        <TouchableOpacity style={styles.reset} onPress={reset} activeOpacity={0.7}>
          <Icons.refresh size={13} color={Colors.textMuted} strokeWidth={2} />
          <Text style={styles.resetText}>New conversation</Text>
        </TouchableOpacity>
      )}

      <ChatInput onSend={handleSend} loading={loading} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.background },
  scroll: { flex: 1 },
  content: { paddingTop: Spacing.lg, paddingBottom: Spacing.md },
  turn: { marginBottom: Spacing.md },
  openers: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.sm, gap: Spacing.sm },
  opener: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md,
    borderRadius: Radius.full, backgroundColor: Colors.surface,
    borderWidth: 1, borderColor: Colors.border,
  },
  openerText: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },
  thinking: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    marginHorizontal: Spacing.lg, marginTop: Spacing.sm,
  },
  thinkingLabel: { ...Typography.caption, color: Colors.textMuted },
  reset: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.xs,
    paddingVertical: Spacing.sm,
  },
  resetText: { ...Typography.caption, color: Colors.textMuted },
});
