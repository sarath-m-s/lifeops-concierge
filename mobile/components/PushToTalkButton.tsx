import React from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { Icons } from '../constants/icons';
import { Colors, Elevation, Radius, Spacing, Typography } from '../constants/theme';

interface Props {
  active: boolean;
  disabled?: boolean;
  onStart: () => void;
  onStop: () => void;
}

/** Hold to talk. The button only gates whether the mic track is publishing —
 * Silero VAD still does the actual end-pointing of the utterance server-side,
 * so a natural mid-sentence pause doesn't cut the user off. */
export function PushToTalkButton({ active, disabled, onStart, onStop }: Props) {
  return (
    <Pressable
      onPressIn={onStart}
      onPressOut={onStop}
      disabled={disabled}
      style={({ pressed }) => [
        styles.button,
        Elevation.raised,
        active && styles.active,
        (disabled || pressed) && !active && styles.disabled,
      ]}
      accessibilityLabel={active ? 'Recording — release to send' : 'Hold to talk'}
    >
      <Icons.mic size={22} color={Colors.textInverse} strokeWidth={2.2} />
      <Text style={styles.label}>{active ? 'Listening…' : 'Hold to talk'}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    minHeight: 52,
    borderRadius: Radius.full,
    backgroundColor: Colors.brand,
    marginHorizontal: Spacing.lg,
    marginBottom: Spacing.md,
  },
  active: { backgroundColor: Colors.brandDark },
  disabled: { opacity: 0.6 },
  label: { ...Typography.bodyStrong, color: Colors.textInverse },
});
