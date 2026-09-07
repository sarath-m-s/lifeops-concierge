import React from 'react';
import { View, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { TimelineView } from '../components/TimelineView';
import { StateView } from '../components/StateView';
import { usePlan } from '../state/PlanContext';
import { Icons } from '../constants/icons';
import { Colors } from '../constants/theme';

export default function PlanScreen() {
  const router = useRouter();
  const { payload, markConfirmed } = usePlan();

  if (!payload) {
    return (
      <StateView
        icon={Icons.plan}
        title="No plan yet"
        body="Ask for a table, some food, or a grocery restock and the steps will show up here."
        actionLabel="Start a plan"
        onAction={() => router.push('/')}
      />
    );
  }

  return (
    <View style={styles.container}>
      <TimelineView payload={payload} onConfirmed={markConfirmed} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
});
