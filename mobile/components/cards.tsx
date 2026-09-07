/** Shared primitives for rendered components. */
import React from 'react';
import { View, Text, Image, TouchableOpacity, StyleSheet } from 'react-native';
import { Colors, Elevation, Radius, Spacing, Typography } from '../constants/theme';

export function Card({ children, onPress, dimmed }: {
  children: React.ReactNode; onPress?: () => void; dimmed?: boolean;
}) {
  const body = (
    <View style={[styles.card, Elevation.card, dimmed && styles.dimmed]}>{children}</View>
  );
  return onPress ? (
    <TouchableOpacity onPress={onPress} activeOpacity={0.85}>{body}</TouchableOpacity>
  ) : body;
}

export function Thumb({ uri }: { uri?: string }) {
  if (!uri) return <View style={[styles.thumb, styles.thumbEmpty]} />;
  return <Image source={{ uri }} style={styles.thumb} resizeMode="cover" />;
}

export function Meta({ children }: { children: React.ReactNode }) {
  return <Text style={styles.meta} numberOfLines={1}>{children}</Text>;
}

export function Title({ children }: { children: React.ReactNode }) {
  return <Text style={styles.title} numberOfLines={2}>{children}</Text>;
}

export function Pill({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'good' | 'warn' }) {
  const map = {
    neutral: [Colors.surfaceSunken, Colors.textSecondary],
    good: [Colors.successTint, Colors.success],
    warn: [Colors.warningTint, Colors.warning],
  }[tone];
  return (
    <View style={[styles.pill, { backgroundColor: map[0] }]}>
      <Text style={[styles.pillText, { color: map[1] }]}>{label}</Text>
    </View>
  );
}

/** Horizontal rail — keeps lists compact inside a chat transcript. */
export function Rail({ children }: { children: React.ReactNode }) {
  return (
    <View style={styles.rail}>{children}</View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
    gap: Spacing.xs,
  },
  dimmed: { opacity: 0.55 },
  thumb: { width: '100%', height: 96, borderRadius: Radius.md, backgroundColor: Colors.surfaceSunken },
  thumbEmpty: { borderWidth: 1, borderColor: Colors.border },
  title: { ...Typography.bodyStrong, color: Colors.textPrimary },
  meta: { ...Typography.caption, color: Colors.textSecondary },
  pill: { alignSelf: 'flex-start', paddingHorizontal: Spacing.sm, paddingVertical: 2, borderRadius: Radius.full },
  pillText: { ...Typography.overline },
  rail: { gap: Spacing.sm },
});
