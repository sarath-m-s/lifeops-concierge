/**
 * The one gate before real money moves. Nothing above this component places an
 * order — /confirm is only ever called from here, after an explicit tap.
 */
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Modal, ActivityIndicator, ScrollView } from 'react-native';
import { UIItem, PendingAction, ConfirmResult } from '../types/agent';
import { SwiggyBadge } from './SwiggyBadge';
import { Icons } from '../constants/icons';
import { api } from '../services/api';
import { Colors, Elevation, Radius, ServiceColor, Spacing, Typography } from '../constants/theme';

interface Props {
  item: UIItem;
  action: PendingAction;
  onConfirmed: () => void;
  onDismiss: () => void;
}

type State = 'idle' | 'working' | 'done' | 'failed';

export function ConfirmationSheet({ item, action, onConfirmed, onDismiss }: Props) {
  const [state, setState] = useState<State>('idle');
  const [result, setResult] = useState<ConfirmResult | null>(null);
  const accent = ServiceColor[item.source] ?? Colors.brand;
  const details = Object.entries(item.details ?? {}).filter(([, v]) => v);

  const handleConfirm = async () => {
    setState('working');
    try {
      const res = await api.confirmAction(action);
      setResult(res);
      setState(res.success ? 'done' : 'failed');
      if (res.success) setTimeout(onConfirmed, 900);
    } catch (e: any) {
      setResult({ success: false, message: e?.message ?? 'Something went wrong.' });
      setState('failed');
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onDismiss}>
      <View style={styles.scrim}>
        <View style={[styles.sheet, Elevation.sheet]}>
          <View style={styles.grabber} />

          <ScrollView showsVerticalScrollIndicator={false}>
            <Text style={styles.eyebrow}>Confirm to continue</Text>
            <Text style={[styles.summary, { color: accent }]}>{action.display_summary}</Text>

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

            <View style={styles.notice}>
              <Icons.shield size={16} color={Colors.brand} strokeWidth={2} />
              <Text style={styles.noticeText}>
                This is the only confirmation. Tapping Confirm places a real order on your Swiggy account.
              </Text>
            </View>

            <SwiggyBadge source={item.source} />

            {state === 'done' && result ? (
              <View style={[styles.result, { backgroundColor: Colors.successTint }]}>
                <Icons.check size={18} color={Colors.success} strokeWidth={2.5} />
                <Text style={[styles.resultText, { color: Colors.success }]}>{result.message}</Text>
              </View>
            ) : null}

            {state === 'failed' && result ? (
              <View style={[styles.result, { backgroundColor: Colors.errorTint }]}>
                <Icons.error size={18} color={Colors.error} strokeWidth={2.5} />
                <Text style={[styles.resultText, { color: Colors.error }]}>{result.message}</Text>
              </View>
            ) : null}
          </ScrollView>

          {state === 'idle' && (
            <View style={styles.actions}>
              <TouchableOpacity style={[styles.cancel, styles.inRow]} onPress={onDismiss} activeOpacity={0.8}>
                <Text style={styles.cancelLabel}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.confirm, styles.inRow, { backgroundColor: accent }]}
                onPress={handleConfirm}
                activeOpacity={0.85}
              >
                <Text style={styles.confirmLabel}>Confirm</Text>
              </TouchableOpacity>
            </View>
          )}

          {state === 'working' && (
            <View style={styles.working}>
              <ActivityIndicator color={accent} />
              <Text style={styles.workingLabel}>Placing with Swiggy…</Text>
            </View>
          )}

          {(state === 'done' || state === 'failed') && (
            <TouchableOpacity style={styles.cancel} onPress={onDismiss} activeOpacity={0.8}>
              <Text style={styles.cancelLabel}>Close</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, backgroundColor: 'rgba(22,24,29,0.5)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: Colors.surface,
    borderTopLeftRadius: Radius.xl,
    borderTopRightRadius: Radius.xl,
    padding: Spacing.xl,
    paddingBottom: Spacing.xxl + Spacing.md,
    maxHeight: '86%',
  },
  grabber: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: Colors.borderStrong,
    alignSelf: 'center',
    marginBottom: Spacing.lg,
  },
  eyebrow: { ...Typography.overline, color: Colors.textMuted, textTransform: 'uppercase' },
  summary: { ...Typography.title, marginTop: Spacing.xs, marginBottom: Spacing.lg },
  details: {
    padding: Spacing.md,
    borderRadius: Radius.md,
    backgroundColor: Colors.surfaceSunken,
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', gap: Spacing.md },
  detailKey: { ...Typography.caption, color: Colors.textMuted, textTransform: 'capitalize' },
  detailValue: { ...Typography.captionStrong, color: Colors.textPrimary, flex: 1, textAlign: 'right' },
  notice: {
    flexDirection: 'row',
    gap: Spacing.sm,
    alignItems: 'flex-start',
    padding: Spacing.md,
    borderRadius: Radius.md,
    backgroundColor: Colors.brandTint,
    marginBottom: Spacing.md,
  },
  noticeText: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },
  result: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    padding: Spacing.md,
    borderRadius: Radius.md,
    marginTop: Spacing.md,
  },
  resultText: { ...Typography.bodyStrong, flex: 1 },
  actions: { flexDirection: 'row', gap: Spacing.md, marginTop: Spacing.xl },
  inRow: { marginTop: 0 },
  cancel: {
    flex: 1,
    minHeight: 50,
    marginTop: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.full,
    borderWidth: 1.5,
    borderColor: Colors.border,
  },
  cancelLabel: { ...Typography.bodyStrong, color: Colors.textSecondary },
  confirm: {
    flex: 2,
    minHeight: 50,
    marginTop: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.full,
  },
  confirmLabel: { ...Typography.bodyStrong, color: Colors.textInverse },
  working: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.xl,
    minHeight: 50,
  },
  workingLabel: { ...Typography.body, color: Colors.textSecondary },
});
