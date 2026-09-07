import React from 'react';
import { View, Text, Switch, TouchableOpacity, ScrollView, StyleSheet, Alert } from 'react-native';
import { SwiggyBadge } from '../components/SwiggyBadge';
import { useAuth } from '../hooks/useAuth';
import { useChat } from '../hooks/useChat';
import { usePlan } from '../state/PlanContext';
import { Icons, LucideIcon } from '../constants/icons';
import { Colors, Elevation, Radius, Spacing, Typography } from '../constants/theme';

export default function SettingsScreen() {
  const { status, connecting, error, connect, disconnect } = useAuth();
  const { clear } = usePlan();
  const { setSpeakerMuted } = useChat();
  const [speakReplies, setSpeakReplies] = React.useState(true);

  const toggleSpeakReplies = (value: boolean) => {
    setSpeakReplies(value);
    setSpeakerMuted(!value);
  };

  const connected = status === 'connected';

  const handleDisconnect = () => {
    Alert.alert(
      'Disconnect Swiggy?',
      'This revokes the session on Swiggy and clears it from this device. Orders you already placed are unaffected.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: async () => {
            await disconnect();
            clear();
          },
        },
      ],
    );
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Section title="Swiggy account" />
      <Card>
        <Row label="Status">
          <View style={styles.statusRow}>
            <View style={[styles.dot, { backgroundColor: connected ? Colors.success : Colors.textMuted }]} />
            <Text style={[styles.statusText, { color: connected ? Colors.success : Colors.textMuted }]}>
              {status === 'checking' ? 'Checking…' : connected ? 'Connected' : 'Not connected'}
            </Text>
          </View>
        </Row>
        <Row label="Sign-in" last={!connected && !error}>
          <Text style={styles.value}>OAuth 2.1 + PKCE</Text>
        </Row>
        {error ? (
          <View style={styles.errorRow}>
            <Icons.error size={15} color={Colors.error} strokeWidth={2} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}
        <TouchableOpacity
          style={styles.actionRow}
          onPress={connected ? handleDisconnect : connect}
          disabled={connecting}
          activeOpacity={0.7}
        >
          <Text style={[styles.actionLabel, connected && styles.destructive]}>
            {connecting ? 'Opening Swiggy…' : connected ? 'Disconnect' : 'Connect Swiggy'}
          </Text>
        </TouchableOpacity>
      </Card>

      <Section title="Voice" />
      <Card>
        <Row label="Speak replies aloud" last>
          <Switch
            value={speakReplies}
            onValueChange={toggleSpeakReplies}
            trackColor={{ true: Colors.brand }}
            thumbColor="#fff"
          />
        </Row>
      </Card>
      <Text style={styles.footnote}>
        Hold the mic button on the Chat tab to talk, or type instead — both go through the same conversation.
      </Text>

      <Section title="Safety" />
      <Card>
        <Note icon={Icons.shield} text="Every order, booking, and checkout needs an explicit confirmation." />
        <Note icon={Icons.refresh} text="Cart state is re-read from Swiggy immediately before anything is placed." />
        <Note icon={Icons.empty} text="Internal Swiggy IDs are never shown to you or read aloud." last />
      </Card>

      <Section title="Data" />
      <Card>
        <View style={styles.note}>
          <Text style={styles.noteText}>
            Your Swiggy access token stays on the server and is never sent to this device. Plans are held in memory
            for the current session only.
          </Text>
        </View>
        <TouchableOpacity style={styles.actionRow} onPress={clear} activeOpacity={0.7}>
          <Text style={styles.actionLabel}>Clear order history</Text>
        </TouchableOpacity>
      </Card>

      <View style={styles.footer}>
        <SwiggyBadge />
        <Text style={styles.version}>LifeOps Concierge v0.4.0</Text>
      </View>
    </ScrollView>
  );
}

function Section({ title }: { title: string }) {
  return <Text style={styles.section}>{title}</Text>;
}

function Card({ children }: { children: React.ReactNode }) {
  return <View style={[styles.card, Elevation.card]}>{children}</View>;
}

function Row({ label, children, last }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <View style={[styles.row, !last && styles.divider]}>
      <Text style={styles.rowLabel}>{label}</Text>
      {children}
    </View>
  );
}

function Note({ icon: Icon, text, last }: { icon: LucideIcon; text: string; last?: boolean }) {
  return (
    <View style={[styles.note, !last && styles.divider]}>
      <Icon size={17} color={Colors.brand} strokeWidth={2} />
      <Text style={styles.noteText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.background },
  content: { paddingBottom: Spacing.xxxl },
  section: {
    ...Typography.overline,
    color: Colors.textMuted,
    textTransform: 'uppercase',
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.xl,
    paddingBottom: Spacing.sm,
  },
  card: {
    marginHorizontal: Spacing.lg,
    borderRadius: Radius.lg,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    minHeight: 50,
  },
  divider: { borderBottomWidth: 1, borderBottomColor: Colors.border },
  rowLabel: { ...Typography.body, color: Colors.textPrimary },
  value: { ...Typography.caption, color: Colors.textSecondary },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { ...Typography.captionStrong },
  actionRow: { paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, minHeight: 50, justifyContent: 'center' },
  actionLabel: { ...Typography.bodyStrong, color: Colors.brand },
  destructive: { color: Colors.error },
  errorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    backgroundColor: Colors.errorTint,
  },
  errorText: { ...Typography.caption, color: Colors.error, flex: 1 },
  note: { flexDirection: 'row', gap: Spacing.md, alignItems: 'flex-start', padding: Spacing.lg },
  noteText: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },
  footnote: {
    ...Typography.caption,
    color: Colors.textMuted,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.sm,
  },
  footer: { alignItems: 'center', gap: Spacing.sm, paddingTop: Spacing.xxl },
  version: { ...Typography.caption, color: Colors.textMuted },
});
