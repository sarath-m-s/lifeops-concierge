import React, { useState } from 'react';
import {
  View, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform,
} from 'react-native';
import { Icons } from '../constants/icons';
import { Colors, Radius, Spacing, Typography } from '../constants/theme';

interface Props {
  onSend: (text: string) => void;
  loading?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, loading, disabled, placeholder }: Props) {
  const [text, setText] = useState('');
  const canSend = text.trim().length > 0 && !loading && !disabled;

  const submit = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText('');
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={styles.bar}>
        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder={placeholder ?? 'Book a table, order food, restock groceries…'}
          placeholderTextColor={Colors.textMuted}
          editable={!disabled}
          multiline
          maxLength={500}
          onSubmitEditing={submit}
          returnKeyType="send"
          blurOnSubmit
        />
        <TouchableOpacity
          style={[styles.send, canSend ? styles.sendOn : styles.sendOff]}
          onPress={submit}
          disabled={!canSend}
          activeOpacity={0.85}
          accessibilityLabel="Send message"
        >
          <Icons.send
            size={18}
            color={canSend ? Colors.textInverse : Colors.textMuted}
            strokeWidth={2.2}
          />
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.xl,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    backgroundColor: Colors.surface,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.md,
    borderRadius: Radius.xl,
    backgroundColor: Colors.surfaceSunken,
    ...Typography.body,
    color: Colors.textPrimary,
  },
  send: {
    width: 44,
    height: 44,
    borderRadius: Radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendOn: { backgroundColor: Colors.brand },
  sendOff: { backgroundColor: Colors.surfaceSunken },
});
