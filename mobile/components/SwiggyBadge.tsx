import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, Radius, ServiceColor, ServiceLabel, Spacing, Typography } from '../constants/theme';

interface Props {
  source?: string;
  /** Compact drops the service name and shows only the colour dot plus "Swiggy". */
  compact?: boolean;
}

export function SwiggyBadge({ source, compact }: Props) {
  const color = source ? ServiceColor[source] ?? Colors.brand : Colors.brand;
  const label = source ? ServiceLabel[source] ?? 'Powered by Swiggy' : 'Powered by Swiggy';

  return (
    <View style={[styles.badge, { borderColor: color + '33', backgroundColor: color + '12' }]}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.label, { color }]} numberOfLines={1}>
        {compact ? 'Swiggy' : label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: Spacing.xs,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 3,
    borderRadius: Radius.full,
    borderWidth: 1,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  label: { ...Typography.overline, textTransform: 'uppercase' },
});
