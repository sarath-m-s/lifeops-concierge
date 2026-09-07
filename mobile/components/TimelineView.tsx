import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { TimelineCard } from './TimelineCard';
import { ConfirmationSheet } from './ConfirmationSheet';
import { StateView } from './StateView';
import { UIItem, UIPayload } from '../types/agent';
import { Icons } from '../constants/icons';
import { Colors, Spacing, Typography } from '../constants/theme';

interface Props {
  payload: UIPayload;
  onConfirmed: (item: UIItem) => void;
}

export function TimelineView({ payload, onConfirmed }: Props) {
  const [active, setActive] = useState<UIItem | null>(null);

  if (!payload.items.length) {
    return (
      <StateView
        icon={Icons.empty}
        title="Nothing to show"
        body="No options came back for that. Try a different area, time, or search."
      />
    );
  }

  const remaining = payload.items.filter((i) => i.status !== 'confirmed').length;

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.head}>
          <Text style={styles.title}>{payload.title ?? 'Your plan'}</Text>
          <Text style={styles.sub}>
            {remaining === 0
              ? 'All steps confirmed.'
              : `${remaining} step${remaining === 1 ? '' : 's'} waiting on you. Nothing is ordered until you confirm.`}
          </Text>
        </View>

        {payload.items.map((item, index) => (
          <TimelineCard
            key={item.action?.display_summary ?? item.title}
            item={item}
            stepNumber={index + 1}
            isLast={index === payload.items.length - 1}
            onConfirm={setActive}
          />
        ))}
      </ScrollView>

      {active?.action ? (
        <ConfirmationSheet
          item={active}
          action={active.action}
          onConfirmed={() => {
            onConfirmed(active);
            setActive(null);
          }}
          onDismiss={() => setActive(null)}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { paddingTop: Spacing.lg, paddingBottom: Spacing.xxxl },
  head: { paddingHorizontal: Spacing.lg, paddingBottom: Spacing.lg, gap: Spacing.xs },
  title: { ...Typography.display, color: Colors.textPrimary },
  sub: { ...Typography.body, color: Colors.textSecondary },
});
