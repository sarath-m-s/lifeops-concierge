/**
 * The screen states that actually happen: nothing yet, nothing found, something
 * broke, not connected. Previously most of these rendered as a blank screen or a
 * raw error string.
 */
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { LucideIcon } from '../constants/icons';
import { Colors, Radius, Spacing, Typography } from '../constants/theme';

interface Props {
  icon: LucideIcon;
  title: string;
  body?: string;
  tone?: 'neutral' | 'error';
  actionLabel?: string;
  onAction?: () => void;
  busy?: boolean;
}

export function StateView({ icon: Icon, title, body, tone = 'neutral', actionLabel, onAction, busy }: Props) {
  const accent = tone === 'error' ? Colors.error : Colors.textMuted;
  const wash = tone === 'error' ? Colors.errorTint : Colors.surfaceSunken;

  return (
    <View style={styles.wrap}>
      <View style={[styles.iconWell, { backgroundColor: wash }]}>
        <Icon size={26} color={accent} strokeWidth={1.75} />
      </View>
      <Text style={styles.title}>{title}</Text>
      {body ? <Text style={styles.body}>{body}</Text> : null}
      {actionLabel && onAction ? (
        <TouchableOpacity style={styles.action} onPress={onAction} disabled={busy} activeOpacity={0.85}>
          {busy ? (
            <ActivityIndicator size="small" color={Colors.textInverse} />
          ) : (
            <Text style={styles.actionLabel}>{actionLabel}</Text>
          )}
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.xxl,
    gap: Spacing.md,
  },
  iconWell: {
    width: 56,
    height: 56,
    borderRadius: Radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.xs,
  },
  title: { ...Typography.heading, color: Colors.textPrimary, textAlign: 'center' },
  body: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center' },
  action: {
    marginTop: Spacing.sm,
    minWidth: 160,
    minHeight: 46,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
    borderRadius: Radius.full,
    backgroundColor: Colors.brand,
  },
  actionLabel: { ...Typography.bodyStrong, color: Colors.textInverse },
});
