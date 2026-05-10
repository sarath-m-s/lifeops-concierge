import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Modal,
  ActivityIndicator, ScrollView,
} from 'react-native';
import { UIItem, PendingAction, ConfirmResult } from '../types/agent';
import { SwiggyBadge } from './SwiggyBadge';
import { api } from '../services/api';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

interface Props {
  item: UIItem;
  action: PendingAction;
  onConfirmed: () => void;
  onDismiss: () => void;
}

export function ConfirmationSheet({ item, action, onConfirmed, onDismiss }: Props) {
  const [state, setState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [result, setResult] = useState<ConfirmResult | null>(null);

  const handleConfirm = async () => {
    setState('loading');
    try {
      // Simulate realistic network delay in mock mode
      await new Promise((r) => setTimeout(r, 1500));
      const res = await api.confirmAction(action);
      setResult(res);
      setState(res.success ? 'success' : 'error');
      if (res.success) {
        setTimeout(onConfirmed, 1200);
      }
    } catch (e: any) {
      setResult({ success: false, message: e.message ?? 'Something went wrong.' });
      setState('error');
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onDismiss}>
      <View style={styles.overlay}>
        <View style={styles.sheet}>
          <View style={styles.handle} />

          <ScrollView showsVerticalScrollIndicator={false}>
            <Text style={styles.heading}>Confirm Action</Text>
            <Text style={styles.summary}>{action.display_summary}</Text>

            <View style={styles.detailsCard}>
              {Object.entries(item.details).filter(([, v]) => v).map(([key, value]) => (
                <View key={key} style={styles.detailRow}>
                  <Text style={styles.detailKey}>{key.replace(/_/g, ' ')}</Text>
                  <Text style={styles.detailValue}>{value}</Text>
                </View>
              ))}
            </View>

            <View style={styles.safetyNote}>
              <Text style={styles.safetyIcon}>🔒</Text>
              <Text style={styles.safetyText}>
                This is the only confirmation. Nothing has been booked or ordered yet.
              </Text>
            </View>

            <SwiggyBadge source={item.source} size="md" />

            {state === 'success' && (
              <View style={styles.successBox}>
                <Text style={styles.successText}>✓ {result?.message}</Text>
              </View>
            )}

            {state === 'error' && (
              <View style={styles.errorBox}>
                <Text style={styles.errorText}>✗ {result?.message}</Text>
              </View>
            )}
          </ScrollView>

          {state === 'idle' && (
            <View style={styles.actions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={onDismiss} activeOpacity={0.8}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleConfirm} activeOpacity={0.8}>
                <Text style={styles.confirmText}>Confirm</Text>
              </TouchableOpacity>
            </View>
          )}

          {state === 'loading' && (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={Colors.swiggyOrange} />
              <Text style={styles.loadingText}>Confirming…</Text>
            </View>
          )}

          {(state === 'success' || state === 'error') && (
            <TouchableOpacity style={styles.doneBtn} onPress={onDismiss} activeOpacity={0.8}>
              <Text style={styles.doneText}>Close</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: Colors.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: Spacing.xl,
    paddingBottom: 40,
    maxHeight: '85%',
  },
  handle: {
    width: 40,
    height: 4,
    backgroundColor: Colors.border,
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: Spacing.lg,
  },
  heading: {
    fontSize: Typography.fontSizeXl,
    fontWeight: Typography.fontWeightBold,
    color: Colors.textPrimary,
    marginBottom: Spacing.xs,
  },
  summary: {
    fontSize: Typography.fontSizeLg,
    color: Colors.swiggyOrange,
    fontWeight: Typography.fontWeightMedium,
    marginBottom: Spacing.lg,
  },
  detailsCard: {
    backgroundColor: Colors.surfaceAlt,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.md,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  detailKey: {
    fontSize: Typography.fontSizeSm,
    color: Colors.textMuted,
    textTransform: 'capitalize',
    flex: 1,
  },
  detailValue: {
    fontSize: Typography.fontSizeSm,
    color: Colors.textPrimary,
    fontWeight: Typography.fontWeightMedium,
    flex: 2,
    textAlign: 'right',
  },
  safetyNote: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFF8F0',
    borderRadius: BorderRadius.sm,
    padding: Spacing.sm,
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  safetyIcon: { fontSize: 16 },
  safetyText: {
    fontSize: Typography.fontSizeXs,
    color: Colors.textSecondary,
    flex: 1,
  },
  successBox: {
    backgroundColor: '#E8F9EF',
    borderRadius: BorderRadius.sm,
    padding: Spacing.md,
    marginTop: Spacing.md,
  },
  successText: {
    color: Colors.success,
    fontWeight: Typography.fontWeightSemibold,
    fontSize: Typography.fontSizeMd,
  },
  errorBox: {
    backgroundColor: '#FFF0F0',
    borderRadius: BorderRadius.sm,
    padding: Spacing.md,
    marginTop: Spacing.md,
  },
  errorText: {
    color: Colors.error,
    fontWeight: Typography.fontWeightSemibold,
    fontSize: Typography.fontSizeMd,
  },
  actions: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginTop: Spacing.xl,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.full,
    borderWidth: 1.5,
    borderColor: Colors.border,
    alignItems: 'center',
  },
  cancelText: {
    color: Colors.textSecondary,
    fontWeight: Typography.fontWeightSemibold,
    fontSize: Typography.fontSizeMd,
  },
  confirmBtn: {
    flex: 2,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.swiggyOrange,
    alignItems: 'center',
  },
  confirmText: {
    color: '#fff',
    fontWeight: Typography.fontWeightBold,
    fontSize: Typography.fontSizeMd,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: Spacing.xl,
    gap: Spacing.sm,
  },
  loadingText: {
    color: Colors.textSecondary,
    fontSize: Typography.fontSizeMd,
  },
  doneBtn: {
    marginTop: Spacing.xl,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.full,
    borderWidth: 1.5,
    borderColor: Colors.border,
    alignItems: 'center',
  },
  doneText: {
    color: Colors.textSecondary,
    fontWeight: Typography.fontWeightSemibold,
    fontSize: Typography.fontSizeMd,
  },
});
