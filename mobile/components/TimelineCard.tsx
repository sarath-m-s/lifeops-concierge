import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { UIItem } from '../types/agent';
import { SwiggyBadge } from './SwiggyBadge';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

interface Props {
  item: UIItem;
  stepNumber: number;
  onConfirm: (item: UIItem) => void;
}

const STATUS_COLORS: Record<string, string> = {
  ready: Colors.swiggyOrange,
  confirmed: Colors.success,
  pending: Colors.textMuted,
  failed: Colors.error,
};

const STATUS_LABELS: Record<string, string> = {
  ready: 'Ready to confirm',
  confirmed: '✓ Confirmed',
  pending: 'Pending',
  failed: 'Failed',
};

export function TimelineCard({ item, stepNumber, onConfirm }: Props) {
  const statusColor = STATUS_COLORS[item.status] ?? Colors.textMuted;
  const isConfirmed = item.status === 'confirmed';

  return (
    <View style={styles.container}>
      <View style={styles.stepCol}>
        <View style={[styles.stepDot, { backgroundColor: statusColor }]}>
          <Text style={styles.stepIcon}>{item.icon ?? String(stepNumber)}</Text>
        </View>
        {stepNumber < 3 && <View style={styles.connector} />}
      </View>

      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.title}>{item.title}</Text>
          <View style={[styles.statusBadge, { borderColor: statusColor }]}>
            <Text style={[styles.statusText, { color: statusColor }]}>{STATUS_LABELS[item.status]}</Text>
          </View>
        </View>

        {item.subtitle && <Text style={styles.subtitle}>{item.subtitle}</Text>}
        {item.time && <Text style={styles.time}>🕗 {item.time}</Text>}

        {Object.entries(item.details).filter(([, v]) => v).map(([key, value]) => (
          <View key={key} style={styles.detailRow}>
            <Text style={styles.detailKey}>{key.replace(/_/g, ' ')}:</Text>
            <Text style={styles.detailValue}>{value}</Text>
          </View>
        ))}

        <View style={styles.footer}>
          <SwiggyBadge source={item.source} size="sm" />
          {!isConfirmed && item.action && (
            <TouchableOpacity
              style={styles.confirmBtn}
              onPress={() => onConfirm(item)}
              activeOpacity={0.8}
            >
              <Text style={styles.confirmBtnText}>Review & Confirm</Text>
            </TouchableOpacity>
          )}
          {isConfirmed && (
            <View style={styles.confirmedTag}>
              <Text style={styles.confirmedTagText}>✓ Done</Text>
            </View>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    marginHorizontal: Spacing.lg,
    marginBottom: Spacing.md,
  },
  stepCol: {
    alignItems: 'center',
    width: 44,
  },
  stepDot: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepIcon: {
    fontSize: 18,
  },
  connector: {
    width: 2,
    flex: 1,
    backgroundColor: Colors.border,
    marginVertical: 4,
    minHeight: 20,
  },
  card: {
    flex: 1,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginLeft: Spacing.sm,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.07,
    shadowRadius: 6,
    elevation: 3,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: Spacing.xs,
    flexWrap: 'wrap',
    gap: Spacing.xs,
  },
  title: {
    fontSize: Typography.fontSizeLg,
    fontWeight: Typography.fontWeightSemibold,
    color: Colors.textPrimary,
    flex: 1,
  },
  statusBadge: {
    borderWidth: 1,
    borderRadius: BorderRadius.full,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
  },
  statusText: {
    fontSize: Typography.fontSizeXs,
    fontWeight: Typography.fontWeightMedium,
  },
  subtitle: {
    fontSize: Typography.fontSizeSm,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  time: {
    fontSize: Typography.fontSizeSm,
    color: Colors.swiggyOrange,
    fontWeight: Typography.fontWeightMedium,
    marginBottom: Spacing.xs,
  },
  detailRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 2,
  },
  detailKey: {
    fontSize: Typography.fontSizeXs,
    color: Colors.textMuted,
    textTransform: 'capitalize',
    marginRight: 4,
  },
  detailValue: {
    fontSize: Typography.fontSizeXs,
    color: Colors.textSecondary,
    flex: 1,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: Spacing.md,
    flexWrap: 'wrap',
    gap: Spacing.sm,
  },
  confirmBtn: {
    backgroundColor: Colors.swiggyOrange,
    borderRadius: BorderRadius.full,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
  },
  confirmBtnText: {
    color: '#fff',
    fontSize: Typography.fontSizeSm,
    fontWeight: Typography.fontWeightSemibold,
  },
  confirmedTag: {
    backgroundColor: '#E8F9EF',
    borderRadius: BorderRadius.full,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
  },
  confirmedTagText: {
    color: Colors.success,
    fontSize: Typography.fontSizeSm,
    fontWeight: Typography.fontWeightMedium,
  },
});
