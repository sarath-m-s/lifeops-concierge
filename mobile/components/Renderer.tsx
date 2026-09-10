/**
 * Component registry. The backend names a type; this maps it to a view.
 *
 * An unknown type renders nothing rather than throwing, so the server can start
 * sending a new component before the app knows how to draw it.
 */
import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { Component, PendingAction } from '../types/agent';
import { Card, Meta, Pill, Thumb, Title } from './cards';
import { Icons } from '../constants/icons';
import { Colors, Radius, Spacing, Typography } from '../constants/theme';

interface Ctx {
  onSuggest: (text: string) => void;
  onConfirm: (action: PendingAction, title: string, total: string) => void;
  confirmingId?: string | null;
  resultFor?: (summary: string) => { ok: boolean; message: string } | undefined;
}

export function Renderer({ components, ctx }: { components?: Component[]; ctx: Ctx }) {
  if (!components?.length) return null;
  return (
    <View style={styles.stack}>
      {components.map((c, i) => (
        <One key={`${c.type}-${i}`} component={c} ctx={ctx} />
      ))}
    </View>
  );
}

function One({ component, ctx }: { component: Component; ctx: Ctx }) {
  const p = component.props ?? {};
  switch (component.type) {
    case 'restaurant_list':
      return <HList items={p.items} render={(r: any) => (
        <Card key={r.name} dimmed={r.open === false} onPress={r.open === false ? undefined : () => ctx.onSuggest(r.name)}>
          <Thumb uri={r.image} />
          <Title>{r.name}</Title>
          {!!r.cuisines && <Meta>{r.cuisines}</Meta>}
          <View style={styles.row}>
            {!!r.rating && <Pill label={`★ ${r.rating}`} tone="good" />}
            {!!r.eta && <Pill label={r.eta} />}
            {r.open === false && <Pill label="Closed" tone="warn" />}
          </View>
          {!!r.cost && <Meta>{r.cost}</Meta>}
          {!!r.offer && <Text style={styles.offer}>{r.offer}</Text>}
        </Card>
      )} />;

    case 'product_list':
      return <HList items={p.items} render={(it: any) => (
        <Card key={it.name + it.unit} dimmed={it.in_stock === false} onPress={it.in_stock === false ? undefined : () => ctx.onSuggest(it.name)}>
          <Thumb uri={it.image} />
          <Title>{it.name}</Title>
          {!!it.unit && <Meta>{it.unit}</Meta>}
          <View style={styles.row}>
            <Text style={styles.price}>₹{it.price}</Text>
            {it.mrp > it.price && <Text style={styles.mrp}>₹{it.mrp}</Text>}
          </View>
          {it.in_stock === false && <Pill label="Out of stock" tone="warn" />}
        </Card>
      )} />;

    case 'menu_list':
      return <VList items={p.items} render={(it: any) => (
        <Card key={it.name} onPress={() => ctx.onSuggest(it.name)}>
          <View style={styles.menuRow}>
            <View style={styles.menuText}>
              <Title>{it.name}</Title>
              {!!it.description && <Meta>{it.description}</Meta>}
              <Text style={styles.price}>₹{it.price}</Text>
            </View>
            {!!it.image && <Thumb uri={it.image} size={64} />}
          </View>
        </Card>
      )} />;

    case 'coupon_list':
      return <VList items={p.items} render={(c: any) => (
        <Card key={c.code} onPress={() => ctx.onSuggest(`Apply ${c.code}`)}>
          <View style={styles.row}>
            <Icons.spark size={15} color={Colors.brand} strokeWidth={2} />
            <Text style={styles.code}>{c.code}</Text>
          </View>
          {!!c.description && <Meta>{c.description}</Meta>}
          {c.online_only && <Pill label="Online payment only" tone="warn" />}
        </Card>
      )} />;

    case 'slot_list':
      return <HList items={p.items} render={(s: any) => (
        <Card key={`${s.date}-${s.time}`} dimmed={!s.free} onPress={!s.free ? undefined : () => ctx.onSuggest(`Book the ${s.time} slot on ${s.date}`)}>
          <Text style={styles.slotTime}>{s.time}</Text>
          <Meta>{s.date}</Meta>
          {!!s.band && <Pill label={s.band} />}
          {s.free ? <Pill label="Free" tone="good" /> : <Pill label="Paid deal" tone="warn" />}
        </Card>
      )} />;

    case 'address_list':
      // A long address list pushes the conversation off screen; show a few and
      // let the user type if the one they want isn't among them.
      return <VList items={(p.items ?? []).slice(0, 4)} render={(a: any) => (
        <Card key={a.address} onPress={() => ctx.onSuggest(`Use my ${a.label} address`)}>
          <View style={styles.row}>
            <Icons.plan size={15} color={Colors.brand} strokeWidth={2} />
            <Text style={styles.code}>{a.label}</Text>
          </View>
          <Meta>{a.address}</Meta>
        </Card>
      )} />;

    case 'order_list':
    case 'order_status':
      return <VList items={p.items} render={(o: any) => (
        <Card key={o.name + o.status} onPress={() => ctx.onSuggest(`Tell me more about my order from ${o.name}`)}>
          <Title>{o.name}</Title>
          <View style={styles.row}>
            {!!o.status && <Pill label={String(o.status)} tone="good" />}
            {!!o.eta && <Meta>{o.eta}</Meta>}
          </View>
          {!!o.total && <Text style={styles.price}>₹{o.total}</Text>}
        </Card>
      )} />;

    case 'confirm_action':
      return <Confirm props={p} ctx={ctx} />;

    case 'chips':
      return (
        <View style={styles.chips}>
          {(p.options ?? []).map((o: string) => (
            <TouchableOpacity key={o} style={styles.chip} onPress={() => ctx.onSuggest(o)} activeOpacity={0.8}>
              <Text style={styles.chipText}>{o}</Text>
            </TouchableOpacity>
          ))}
        </View>
      );

    default:
      // Unknown component type — the server is ahead of the app. Render nothing.
      return null;
  }
}

function Confirm({ props, ctx }: { props: any; ctx: Ctx }) {
  const action: PendingAction | undefined = props.action;
  const summary = action?.display_summary ?? '';
  const result = ctx.resultFor?.(summary);
  const busy = ctx.confirmingId === summary;

  return (
    <View style={styles.confirm}>
      <Text style={styles.confirmTitle}>{props.title}</Text>
      {(props.lines ?? []).map((l: any) => (
        <View key={l.label + l.value} style={styles.lineRow}>
          <Text style={styles.lineLabel} numberOfLines={1}>{l.label}</Text>
          <Text style={styles.lineValue}>{l.value}</Text>
        </View>
      ))}
      <View style={styles.totalRow}>
        <Text style={styles.totalLabel}>Total</Text>
        <Text style={styles.totalValue}>{props.total}</Text>
      </View>

      {result ? (
        <View style={[styles.resultBox, { backgroundColor: result.ok ? Colors.successTint : Colors.errorTint }]}>
          {result.ok
            ? <Icons.check size={16} color={Colors.success} strokeWidth={2.5} />
            : <Icons.error size={16} color={Colors.error} strokeWidth={2.5} />}
          <Text style={[styles.resultText, { color: result.ok ? Colors.success : Colors.error }]}>
            {result.message}
          </Text>
        </View>
      ) : (
        <>
          <View style={styles.noticeRow}>
            <Icons.shield size={14} color={Colors.brand} strokeWidth={2} />
            <Text style={styles.notice}>{props.note ?? 'This places a real order.'}</Text>
          </View>
          <TouchableOpacity
            style={[styles.cta, busy && styles.ctaBusy]}
            disabled={busy || !action}
            onPress={() => action && ctx.onConfirm(action, props.title, props.total)}
            activeOpacity={0.85}
          >
            {busy ? <ActivityIndicator size="small" color={Colors.textInverse} />
                  : <Text style={styles.ctaText}>Confirm</Text>}
          </TouchableOpacity>
        </>
      )}
    </View>
  );
}

function HList({ items, render }: { items?: any[]; render: (x: any) => React.ReactNode }) {
  if (!items?.length) return null;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hlist}>
      {items.map((it, i) => <View key={i} style={styles.hitem}>{render(it)}</View>)}
    </ScrollView>
  );
}

function VList({ items, render }: { items?: any[]; render: (x: any) => React.ReactNode }) {
  if (!items?.length) return null;
  return <View style={styles.vlist}>{items.map((it, i) => <View key={i}>{render(it)}</View>)}</View>;
}

const styles = StyleSheet.create({
  stack: { gap: Spacing.md, marginTop: Spacing.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, flexWrap: 'wrap' },
  hlist: { paddingHorizontal: Spacing.lg, gap: Spacing.sm },
  hitem: { width: 190 },
  vlist: { paddingHorizontal: Spacing.lg, gap: Spacing.sm },
  offer: { ...Typography.caption, color: Colors.brand, fontWeight: '600' },
  price: { ...Typography.bodyStrong, color: Colors.textPrimary },
  mrp: { ...Typography.caption, color: Colors.textMuted, textDecorationLine: 'line-through' },
  code: { ...Typography.bodyStrong, color: Colors.textPrimary },
  slotTime: { ...Typography.heading, color: Colors.textPrimary },
  menuRow: { flexDirection: 'row', gap: Spacing.md, alignItems: 'flex-start' },
  menuText: { flex: 1, gap: 2 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, paddingHorizontal: Spacing.lg },
  chip: {
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderRadius: Radius.full, backgroundColor: Colors.surface,
    borderWidth: 1, borderColor: Colors.border,
  },
  chipText: { ...Typography.caption, color: Colors.textSecondary },
  confirm: {
    marginHorizontal: Spacing.lg, padding: Spacing.lg,
    borderRadius: Radius.lg, backgroundColor: Colors.surface,
    borderWidth: 1.5, borderColor: Colors.brand, gap: Spacing.sm,
  },
  confirmTitle: { ...Typography.heading, color: Colors.textPrimary },
  lineRow: { flexDirection: 'row', justifyContent: 'space-between', gap: Spacing.md },
  lineLabel: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },
  lineValue: { ...Typography.captionStrong, color: Colors.textPrimary },
  totalRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    borderTopWidth: 1, borderTopColor: Colors.border, paddingTop: Spacing.sm, marginTop: Spacing.xs,
  },
  totalLabel: { ...Typography.bodyStrong, color: Colors.textPrimary },
  totalValue: { ...Typography.bodyStrong, color: Colors.brand },
  noticeRow: { flexDirection: 'row', gap: Spacing.sm, alignItems: 'flex-start', marginTop: Spacing.xs },
  notice: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },
  cta: {
    marginTop: Spacing.sm, minHeight: 46, borderRadius: Radius.full,
    backgroundColor: Colors.brand, alignItems: 'center', justifyContent: 'center',
  },
  ctaBusy: { opacity: 0.7 },
  ctaText: { ...Typography.bodyStrong, color: Colors.textInverse },
  resultBox: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    padding: Spacing.md, borderRadius: Radius.md, marginTop: Spacing.sm,
  },
  resultText: { ...Typography.captionStrong, flex: 1 },
});
