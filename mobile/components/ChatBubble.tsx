import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ChatMessage } from '../types/agent';
import { Icons } from '../constants/icons';
import { Colors, Radius, Spacing, Typography } from '../constants/theme';

export function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  if (message.failed) {
    return (
      <View style={styles.rowAssistant}>
        <View style={styles.failed}>
          <Icons.error size={15} color={Colors.error} strokeWidth={2} />
          <Text style={styles.failedText}>{message.text}</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}>
      <View style={[styles.bubble, isUser ? styles.user : styles.assistant]}>
        <Text style={[styles.text, isUser ? styles.textUser : styles.textAssistant]}>{message.text}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { paddingHorizontal: Spacing.lg, flexDirection: 'row' },
  rowUser: { justifyContent: 'flex-end' },
  rowAssistant: { justifyContent: 'flex-start', paddingHorizontal: Spacing.lg, flexDirection: 'row' },
  bubble: { maxWidth: '86%', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  user: { backgroundColor: Colors.brand, borderRadius: Radius.lg, borderBottomRightRadius: Radius.sm },
  assistant: {
    backgroundColor: Colors.surface, borderRadius: Radius.lg, borderBottomLeftRadius: Radius.sm,
    borderWidth: 1, borderColor: Colors.border,
  },
  text: { ...Typography.body },
  textUser: { color: Colors.textInverse },
  textAssistant: { color: Colors.textPrimary },
  failed: {
    flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm, maxWidth: '90%',
    backgroundColor: Colors.errorTint, borderRadius: Radius.md, padding: Spacing.md,
  },
  failedText: { ...Typography.caption, color: Colors.error, flex: 1 },
});
