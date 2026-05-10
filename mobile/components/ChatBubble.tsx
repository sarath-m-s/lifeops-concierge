import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ChatMessage } from '../types/agent';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

interface Props {
  message: ChatMessage;
}

export function ChatBubble({ message }: Props) {
  const isUser = message.role === 'user';

  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}>
      {!isUser && <View style={styles.avatar}><Text style={styles.avatarText}>🤖</Text></View>}
      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
        <Text style={[styles.text, isUser ? styles.textUser : styles.textAssistant]}>
          {message.text}
        </Text>
        {message.spoken && (
          <Text style={styles.spokenIndicator}>🔊</Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    marginVertical: Spacing.xs,
    marginHorizontal: Spacing.lg,
    alignItems: 'flex-end',
  },
  rowUser: {
    justifyContent: 'flex-end',
  },
  rowAssistant: {
    justifyContent: 'flex-start',
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: Colors.surfaceAlt,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: Spacing.sm,
  },
  avatarText: {
    fontSize: 16,
  },
  bubble: {
    maxWidth: '78%',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.lg,
  },
  bubbleUser: {
    backgroundColor: Colors.userBubble,
    borderBottomRightRadius: 4,
  },
  bubbleAssistant: {
    backgroundColor: Colors.assistantBubble,
    borderBottomLeftRadius: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 2,
  },
  text: {
    fontSize: Typography.fontSizeMd,
    lineHeight: 22,
  },
  textUser: {
    color: Colors.userBubbleText,
  },
  textAssistant: {
    color: Colors.assistantBubbleText,
  },
  spokenIndicator: {
    fontSize: 10,
    marginTop: 2,
    textAlign: 'right',
  },
});
