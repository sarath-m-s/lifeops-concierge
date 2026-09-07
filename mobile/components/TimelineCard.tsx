import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { UIItem } from '../types/agent';
import { SwiggyBadge } from './SwiggyBadge';
import { Icons, stepIcon } from '../constants/icons';
import { Colors, Elevation, Radius, ServiceColor, Spacing, Typography } from '../constants/theme';

interface Props {
  item: UIItem;
  stepNumber: number;
  /** Drives the connector rail — the last card must not draw one. */
  isLast: boolean;
  onConfirm: (item: UIItem) => void;
}

const STATUS: Record<string, { label: string; color: string; tint: string }> = {
  ready: { label: 'Ready', color: Colors.brand, tint: Colors.brandTint },
  confirmed: { label: 'Confirmed', color: Colors.success, tint: Colors.successTint },
  pending: { label: 'Pending', color: Colors.textMuted, tint: Colors.surfaceSunken },
  failed: { label: 'Failed', color: Colors.error, tint: Colors.errorTint },
};

export function TimelineCard({ item, stepNumber, isLast, onConfirm }: Props) {
  const status = STATUS[item.status] ?? STATUS.pending;
  const accent = ServiceColor[item.source] ?? Colors.brand;
  const StepIcon = stepIcon(item.category, item.source);
  const isConfirmed = item.status === 'confirmed';
  const details = Object.entries(item.details ?? {}).filter(([, v]) => v);

  return (
    <View style={styles.row}>
      <View style={styles.rail}>
        <View style={[styles.node, { backgroundColor: accent }]}>
          {isConfirmed ? (
            <Icons.check size={18} color={Colors.textInverse} strokeWidth={2.5} />
          ) : (
            <StepIcon size={18} color={Colors.textInverse} strokeWidth={2} />
          )}
        </View>
        {!isLast && <View style={styles.connector} />}
      </View>

      <View style={[styles.card, Elevation.card]}>
        <View style={styles.header}>
          <Text style={styles.step}>Step {stepNumber}</Text>
          <View style={[styles.status, { backgroundColor: status.tint }]}>
            <Text style={[styles.statusLabel, { color: status.color }]}>{status.label}</Text>
          </View>
        </View>

        <Text style={styles.title}>{item.title}</Text>
        {item.subtitle ? <Text style={styles.subtitle}>{item.subtitle}</Text> : null}

        {item.time ? (
          <View style={styles.timeRow}>
            <Icons.clock size={14} color={accent} strokeWidth={2} />
            <Text style={[styles.time, { color: accent }]}>{item.time}</Text>
          </View>
        ) : null}

        {details.length > 0 && (
          <View style={styles.details}>
            {details.map(([key, value]) => (
              <View key={key} style={styles.detailRow}>
                <Text style={styles.detailKey}>{key.replace(/_/g, ' ')}</Text>
                <Text style={styles.detailValue}>{value}</Text>
              </View>
            ))}
          </View>
        )}

        <View style={styles.footer}>
          <SwiggyBadge source={item.source} />
          {!isConfirmed && item.action ? (
            <TouchableOpacity
              style={[styles.cta, { backgroundColor: accent }]}
              onPress={() => onConfirm(item)}
              activeOpacity={0.85}
            >
              <Text style={styles.ctaLabel}>Review</Text>
              <Icons.chevron size={16} color={Colors.textInverse} strokeWidth={2.5} />
            </TouchableOpacity>
          ) : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', paddingHorizontal: Spacing.lg, paddingBottom: Spacing.md },
  rail: { width: 40, alignItems: 'center' },
  node: {
    width: 36,
    height: 36,
    borderRadius: Radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  connector: { width: 2, flex: 1, minHeight: 24, backgroundColor: Colors.border, marginTop: Spacing.xs },
  card: {
    flex: 1,
    marginLeft: Spacing.md,
    padding: Spacing.lg,
    borderRadius: Radius.lg,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  step: { ...Typography.overline, color: Colors.textMuted, textTransform: 'uppercase' },
  status: { paddingHorizontal: Spacing.sm, paddingVertical: 3, borderRadius: Radius.full },
  statusLabel: { ...Typography.overline },
  title: { ...Typography.heading, color: Colors.textPrimary, marginTop: Spacing.sm },
  subtitle: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2 },
  timeRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs, marginTop: Spacing.sm },
  time: { ...Typography.captionStrong },
  details: {
    marginTop: Spacing.md,
    padding: Spacing.md,
    borderRadius: Radius.md,
    backgroundColor: Colors.surfaceSunken,
    gap: Spacing.xs,
  },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', gap: Spacing.md },
  detailKey: { ...Typography.caption, color: Colors.textMuted, textTransform: 'capitalize', flexShrink: 0 },
  detailValue: { ...Typography.caption, color: Colors.textPrimary, flex: 1, textAlign: 'right' },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: Spacing.lg,
    gap: Spacing.sm,
  },
  cta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    minHeight: 36,
    paddingLeft: Spacing.lg,
    paddingRight: Spacing.md,
    borderRadius: Radius.full,
  },
  ctaLabel: { ...Typography.captionStrong, color: Colors.textInverse },
});
