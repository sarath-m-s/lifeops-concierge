/**
 * Actions the user has acted on, shared between Chat and the Plan tab.
 *
 * Confirmation now happens inline in the conversation, so the Plan tab is no
 * longer where work happens — it's the record of what's been placed.
 */
import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { PendingAction, TrackedAction } from '../types/agent';

interface PlanState {
  actions: TrackedAction[];
  results: Record<string, { ok: boolean; message: string }>;
  record: (action: PendingAction, title: string, total: string) => void;
  settle: (summary: string, ok: boolean, message: string) => void;
  clear: () => void;
}

const Ctx = createContext<PlanState | null>(null);

function sourceOf(action: PendingAction): TrackedAction['source'] {
  if (action.action_type === 'book_table') return 'dineout';
  if (action.action_type === 'checkout_instamart') return 'instamart';
  return 'food';
}

export function PlanProvider({ children }: { children: React.ReactNode }) {
  const [actions, setActions] = useState<TrackedAction[]>([]);
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string }>>({});

  const record = useCallback((action: PendingAction, title: string, total: string) => {
    setActions((prev) => {
      // display_summary is the identity: the same proposal re-rendered must not
      // create a second row.
      if (prev.some((a) => a.id === action.display_summary)) return prev;
      return [
        ...prev,
        {
          id: action.display_summary,
          title,
          summary: action.display_summary,
          total,
          source: sourceOf(action),
          status: 'pending',
        },
      ];
    });
  }, []);

  const settle = useCallback((summary: string, ok: boolean, message: string) => {
    setResults((prev) => ({ ...prev, [summary]: { ok, message } }));
    setActions((prev) =>
      prev.map((a) =>
        a.id === summary ? { ...a, status: ok ? 'confirmed' : 'failed', message } : a,
      ),
    );
  }, []);

  const clear = useCallback(() => {
    setActions([]);
    setResults({});
  }, []);

  const value = useMemo(() => ({ actions, results, record, settle, clear }), [actions, results, record, settle, clear]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePlan(): PlanState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('usePlan must be used inside PlanProvider');
  return ctx;
}
