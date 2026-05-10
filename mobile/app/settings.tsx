import React, { useState } from 'react';
import { View, Text, Switch, TouchableOpacity, ScrollView, StyleSheet, Alert } from 'react-native';
import { SwiggyBadge } from '../components/SwiggyBadge';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

export default function SettingsScreen() {
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [cuisinePrefs] = useState(['Italian', 'Continental', 'Desserts']);
  const [dietary] = useState(['No pork']);

  const handleClearData = () => {
    Alert.alert(
      'Clear All Data',
      'This will clear your session, plan summaries, and preferences. Voice transcripts are already session-only.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Clear', style: 'destructive', onPress: () => Alert.alert('Done', 'All local data cleared.') },
      ]
    );
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Account */}
      <SectionHeader title="Swiggy Account" />
      <Card>
        <Row label="Status">
          <View style={styles.connectedRow}>
            <View style={styles.connectedDot} />
            <Text style={styles.connectedText}>Connected (Mock Mode)</Text>
          </View>
        </Row>
        <Row label="Auth" last>
          <Text style={styles.valueText}>OAuth 2.1 + PKCE</Text>
        </Row>
      </Card>

      {/* Voice */}
      <SectionHeader title="Voice & Audio" />
      <Card>
        <Row label="Voice Input">
          <Switch
            value={voiceEnabled}
            onValueChange={setVoiceEnabled}
            trackColor={{ true: Colors.swiggyOrange }}
            thumbColor="#fff"
          />
        </Row>
        <Row label="TTS Playback" last>
          <Switch
            value={ttsEnabled}
            onValueChange={setTtsEnabled}
            trackColor={{ true: Colors.swiggyOrange }}
            thumbColor="#fff"
          />
        </Row>
      </Card>

      {/* Preferences */}
      <SectionHeader title="Preferences" />
      <Card>
        <Row label="Cuisine">
          <Text style={styles.valueText}>{cuisinePrefs.join(', ')}</Text>
        </Row>
        <Row label="Dietary notes" last>
          <Text style={styles.valueText}>{dietary.join(', ')}</Text>
        </Row>
      </Card>

      {/* Safety */}
      <SectionHeader title="Safety" />
      <Card>
        <View style={styles.safetyItem}>
          <Text style={styles.safetyIcon}>🔒</Text>
          <Text style={styles.safetyText}>Confirmation required before every order, booking, or checkout</Text>
        </View>
        <View style={[styles.safetyItem, { borderTopWidth: 1, borderTopColor: Colors.border }]}>
          <Text style={styles.safetyIcon}>🚫</Text>
          <Text style={styles.safetyText}>Internal IDs never shown to you or spoken aloud</Text>
        </View>
        <View style={[styles.safetyItem, { borderTopWidth: 1, borderTopColor: Colors.border }]}>
          <Text style={styles.safetyIcon}>🔄</Text>
          <Text style={styles.safetyText}>Cart state refreshed before every mutation</Text>
        </View>
      </Card>

      {/* Data & Privacy */}
      <SectionHeader title="Data & Privacy" />
      <Card>
        <View style={styles.privacyNote}>
          <Text style={styles.privacyText}>
            Voice transcripts are session-only. Plan summaries cleared after 24 hours. No payment details stored.
          </Text>
        </View>
        <TouchableOpacity style={styles.dangerRow} onPress={handleClearData}>
          <Text style={styles.dangerText}>Clear all data</Text>
        </TouchableOpacity>
      </Card>

      {/* Attribution */}
      <View style={styles.footer}>
        <SwiggyBadge size="md" />
        <Text style={styles.version}>LifeOps Concierge v0.2.0 · Phase 2</Text>
      </View>
    </ScrollView>
  );
}

function SectionHeader({ title }: { title: string }) {
  return <Text style={sectionStyles.header}>{title}</Text>;
}

function Card({ children }: { children: React.ReactNode }) {
  return <View style={cardStyles.card}>{children}</View>;
}

function Row({ label, children, last }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <View style={[rowStyles.row, !last && rowStyles.border]}>
      <Text style={rowStyles.label}>{label}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { paddingBottom: 48 },
  connectedRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  connectedDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.success },
  connectedText: { fontSize: Typography.fontSizeSm, color: Colors.success, fontWeight: '600' },
  valueText: { fontSize: Typography.fontSizeSm, color: Colors.textSecondary, maxWidth: 180, textAlign: 'right' },
  safetyItem: { flexDirection: 'row', alignItems: 'flex-start', padding: Spacing.md, gap: Spacing.sm },
  safetyIcon: { fontSize: 16 },
  safetyText: { fontSize: Typography.fontSizeSm, color: Colors.textSecondary, flex: 1, lineHeight: 20 },
  privacyNote: { padding: Spacing.md },
  privacyText: { fontSize: Typography.fontSizeSm, color: Colors.textSecondary, lineHeight: 20 },
  dangerRow: { padding: Spacing.md, borderTopWidth: 1, borderTopColor: Colors.border },
  dangerText: { fontSize: Typography.fontSizeMd, color: Colors.error, fontWeight: '600' },
  footer: { alignItems: 'center', gap: Spacing.sm, paddingTop: Spacing.xl },
  version: { fontSize: Typography.fontSizeXs, color: Colors.textMuted },
});

const sectionStyles = StyleSheet.create({
  header: {
    fontSize: Typography.fontSizeXs,
    fontWeight: '700',
    color: Colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.xl,
    paddingBottom: Spacing.xs,
  },
});

const cardStyles = StyleSheet.create({
  card: {
    backgroundColor: Colors.surface,
    marginHorizontal: Spacing.lg,
    borderRadius: BorderRadius.lg,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
});

const rowStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.md,
  },
  border: { borderBottomWidth: 1, borderBottomColor: Colors.border },
  label: { fontSize: Typography.fontSizeMd, color: Colors.textPrimary },
});
