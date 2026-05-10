import React, { useState, useCallback } from 'react';
import { View, TextInput, TouchableOpacity, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { VoiceButton } from './VoiceButton';
import { useVoice } from '../hooks/useVoice';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

interface Props {
  onSend: (text: string) => void;
  loading?: boolean;
}

export function ChatInput({ onSend, loading }: Props) {
  const [input, setInput] = useState('');

  const handleTranscript = useCallback((text: string) => {
    setInput(text);
  }, []);

  const { voiceState, startListening } = useVoice(handleTranscript);

  const handleSend = () => {
    const text = input.trim();
    if (!text || loading) return;
    onSend(text);
    setInput('');
  };

  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Ask me to plan your evening..."
          placeholderTextColor={Colors.textMuted}
          multiline
          returnKeyType="send"
          onSubmitEditing={handleSend}
        />
        <VoiceButton state={voiceState} onPress={startListening} />
        <TouchableOpacity
          style={[styles.sendBtn, (!input.trim() || loading) && styles.sendBtnDisabled]}
          onPress={handleSend}
          disabled={!input.trim() || loading}
          activeOpacity={0.8}
        >
          {loading ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <Text style={styles.sendIcon}>➤</Text>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.surface,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    paddingBottom: Spacing.lg,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: Spacing.sm,
  },
  input: {
    flex: 1,
    backgroundColor: Colors.surfaceAlt,
    borderRadius: BorderRadius.xl,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    fontSize: Typography.fontSizeMd,
    color: Colors.textPrimary,
    maxHeight: 100,
    minHeight: 44,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.swiggyOrange,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: Colors.border,
  },
  sendIcon: {
    color: '#fff',
    fontSize: 18,
  },
});
