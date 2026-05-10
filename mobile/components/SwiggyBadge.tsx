import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

interface Props {
  source?: 'dineout' | 'food' | 'instamart';
  size?: 'sm' | 'md';
}

const SOURCE_LABELS: Record<string, string> = {
  dineout: 'Swiggy Dineout',
  food: 'Swiggy Food',
  instamart: 'Swiggy Instamart',
};

export function SwiggyBadge({ source, size = 'sm' }: Props) {
  const label = source ? SOURCE_LABELS[source] : 'Powered by Swiggy';
  const isSmall = size === 'sm';

  return (
    <View style={styles.badge}>
      <View style={styles.dot} />
      <Text style={[styles.text, isSmall && styles.textSm]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFF4EC',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 3,
    borderRadius: BorderRadius.full,
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: '#FFD4B0',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: Colors.swiggyOrange,
    marginRight: 5,
  },
  text: {
    fontSize: Typography.fontSizeSm,
    color: Colors.swiggyOrange,
    fontWeight: Typography.fontWeightSemibold,
  },
  textSm: {
    fontSize: Typography.fontSizeXs,
  },
});
