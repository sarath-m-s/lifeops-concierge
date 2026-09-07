import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, ScrollView, StyleSheet, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { ChatBubble } from '../components/ChatBubble';
import { ChatInput } from '../components/ChatInput';
import { PushToTalkButton } from '../components/PushToTalkButton';
import { Renderer } from '../components/Renderer';
import { StateView } from '../components/StateView';
import { usePlan } from '../state/PlanContext';
import { useChat } from '../hooks/useChat';
import { useAuth } from '../hooks/useAuth';
import { api } from '../services/api';
import { PendingAction } from '../types/agent';
import { Icons } from '../constants/icons';
import { Colors, Radius, Spacing, Typography } from '../constants/theme';

const OPENERS = [
  'What can I order near me?',
  'Any coffee deals on Instamart?',
  'Book a table for two this Friday',
];

export default function ChatScreen() {
  const {
    messages, caption, connectionState, micActive,
    connect: joinRoom, sendText, startTalking, stopTalking, reset,
  } = useChat();
  const { status, connecting, connect: connectSwiggy } = useAuth();
  const { record, settle, results } = usePlan();
  const [confirming, setConfirming] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 90);
    return () => clearTimeout(t);
  }, [messages.length, caption]);

  const handleConfirm = useCallback(async (action: PendingAction, title: string, total: string) => {
    record(action, title, total);
    setConfirming(action.display_summary);
    try {
      const res = await api.confirmAction(action);
      settle(action.display_summary, res.success, res.message);
      // The agent speaks and re-states the outcome itself (see backend
      // app/routers/confirm.py's room signal) — no client-side TTS anymore.
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
        onAction={connectSwiggy}
        busy={connecting}
      />
    );
  }

  if (connectionState !== 'connected') {
    return (
      <StateView
        icon={Icons.mic}
        title="Start a conversation"
        body={
          connectionState === 'reconnecting'
            ? 'Reconnecting…'
            : 'Talk or type to your concierge. Voice and text both go through one live conversation.'
        }
        actionLabel="Start conversation"
        onAction={joinRoom}
        busy={connectionState === 'connecting'}
      />
    );
  }

  const ctx = {
    onSuggest: sendText,
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
              <TouchableOpacity key={s} style={styles.opener} onPress={() => sendText(s)} activeOpacity={0.8}>
                <Icons.spark size={14} color={Colors.brand} strokeWidth={2} />
                <Text style={styles.openerText}>{s}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {caption && (
          <View style={styles.turn}>
            <View style={caption.role === 'user' ? styles.captionRowUser : styles.captionRowAssistant}>
              <Text style={styles.captionText}>{caption.text}</Text>
            </View>
          </View>
        )}
      </ScrollView>

      {messages.length > 1 && (
        <TouchableOpacity style={styles.reset} onPress={reset} activeOpacity={0.7}>
          <Icons.refresh size={13} color={Colors.textMuted} strokeWidth={2} />
          <Text style={styles.resetText}>New conversation</Text>
        </TouchableOpacity>
      )}

      <PushToTalkButton active={micActive} onStart={startTalking} onStop={stopTalking} />
      <ChatInput onSend={sendText} placeholder="Or type here…" />
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
  captionRowUser: { paddingHorizontal: Spacing.lg, alignItems: 'flex-end' },
  captionRowAssistant: { paddingHorizontal: Spacing.lg, alignItems: 'flex-start' },
  captionText: { ...Typography.caption, color: Colors.textMuted, fontStyle: 'italic' },
  reset: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.xs,
    paddingVertical: Spacing.sm,
  },
  resetText: { ...Typography.caption, color: Colors.textMuted },
});
