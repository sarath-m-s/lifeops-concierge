import React from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { StateView } from '../components/StateView';
import { SwiggyBadge } from '../components/SwiggyBadge';
import { usePlan } from '../state/PlanContext';
import { Icons } from '../constants/icons';
import { Colors, Elevation, Radius, ServiceColor, Spacing, Typography } from '../constants/theme';

export default function PlanScreen() {
  const { actions } = usePlan();

  if (!actions.length) {
    return (
      <StateView
        icon={Icons.plan}
        title="Nothing placed yet"
        body="Orders and bookings you confirm in the conversation show up here."
      />
    );
  }

  const done = actions.filter((a) => a.status === 'confirmed').length;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.head}>
        <Text style={styles.title}>Your orders</Text>
        <Text style={styles.sub}>
          {done} of {actions.length} confirmed
        </Text>
      </View>

      {actions.map((a) => {
        const accent = ServiceColor[a.source] ?? Colors.brand;
        const tone =
          a.status === 'confirmed' ? [Colors.successTint, Colors.success, 'Confirmed']
          : a.status === 'failed' ? [Colors.errorTint, Colors.error, 'Failed']
          : [Colors.surfaceSunken, Colors.textMuted, 'Pending'];
        return (
          <View key={a.id} style={[styles.card, Elevation.card]}>
            <View style={styles.cardHead}>
              <View style={[styles.dot, { backgroundColor: accent }]} />
              <Text style={styles.cardTitle} numberOfLines={1}>{a.title}</Text>
              <View style={[styles.pill, { backgroundColor: tone[0] }]}>
                <Text style={[styles.pillText, { color: tone[1] }]}>{tone[2]}</Text>
              </View>
            </View>
            <Text style={styles.summary}>{a.summary}</Text>
            {!!a.message && <Text style={[styles.message, { color: tone[1] }]}>{a.message}</Text>}
            <View style={styles.cardFoot}>
              <SwiggyBadge source={a.source} />
              <Text style={styles.total}>{a.total}</Text>
            </View>
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.background },
  content: { paddingTop: Spacing.lg, paddingBottom: Spacing.xxxl },
  head: { paddingHorizontal: Spacing.lg, paddingBottom: Spacing.lg, gap: Spacing.xs },
  title: { ...Typography.display, color: Colors.textPrimary },
  sub: { ...Typography.body, color: Colors.textSecondary },
  card: {
    marginHorizontal: Spacing.lg, marginBottom: Spacing.md, padding: Spacing.lg,
    borderRadius: Radius.lg, backgroundColor: Colors.surface,
    borderWidth: 1, borderColor: Colors.border, gap: Spacing.sm,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  cardTitle: { ...Typography.heading, color: Colors.textPrimary, flex: 1 },
  pill: { paddingHorizontal: Spacing.sm, paddingVertical: 2, borderRadius: Radius.full },
  pillText: { ...Typography.overline },
  summary: { ...Typography.caption, color: Colors.textSecondary },
  message: { ...Typography.captionStrong },
  cardFoot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: Spacing.xs },
  total: { ...Typography.bodyStrong, color: Colors.textPrimary },
});
