import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { UIItem, UIPayload, PendingAction } from '../types/agent';
import { TimelineCard } from './TimelineCard';
import { ConfirmationSheet } from './ConfirmationSheet';
import { Colors, Spacing, Typography } from '../constants/theme';

interface Props {
  payload: UIPayload;
}

export function TimelineView({ payload }: Props) {
  const [items, setItems] = useState<UIItem[]>(payload.items as UIItem[]);
  const [selectedItem, setSelectedItem] = useState<UIItem | null>(null);

  const handleConfirm = (item: UIItem) => {
    setSelectedItem(item);
  };

  const handleConfirmed = (confirmedItem: UIItem) => {
    setItems((prev) =>
      prev.map((i) => (i.title === confirmedItem.title ? { ...i, status: 'confirmed' } : i))
    );
    setSelectedItem(null);
  };

  const handleDismiss = () => {
    setSelectedItem(null);
  };

  const confirmedCount = items.filter((i) => i.status === 'confirmed').length;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>{payload.title ?? 'Your Plan'}</Text>
        <Text style={styles.progress}>
          {confirmedCount}/{items.length} confirmed
        </Text>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.list}>
        {items.map((item, index) => (
          <TimelineCard
            key={item.title + index}
            item={item}
            stepNumber={index + 1}
            onConfirm={handleConfirm}
          />
        ))}
        <View style={styles.footer}>
          <Text style={styles.footerText}>Powered by Swiggy · All actions require your confirmation</Text>
        </View>
      </ScrollView>

      {selectedItem?.action && (
        <ConfirmationSheet
          item={selectedItem}
          action={selectedItem.action}
          onConfirmed={() => handleConfirmed(selectedItem)}
          onDismiss={handleDismiss}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    backgroundColor: Colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  title: {
    fontSize: Typography.fontSizeXl,
    fontWeight: Typography.fontWeightBold,
    color: Colors.textPrimary,
  },
  progress: {
    fontSize: Typography.fontSizeSm,
    color: Colors.swiggyOrange,
    fontWeight: Typography.fontWeightMedium,
  },
  list: {
    paddingTop: Spacing.lg,
    paddingBottom: Spacing.xxl,
  },
  footer: {
    alignItems: 'center',
    paddingTop: Spacing.lg,
    paddingHorizontal: Spacing.xl,
  },
  footerText: {
    fontSize: Typography.fontSizeXs,
    color: Colors.textMuted,
    textAlign: 'center',
  },
});
