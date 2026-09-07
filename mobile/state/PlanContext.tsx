/**
 * The current plan, shared between the Chat and Plan tabs.
 *
 * This replaces a module-level `let` that survived nothing and could not trigger
 * a re-render — switching tabs showed whatever the variable happened to hold.
 */
import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { UIItem, UIPayload } from '../types/agent';

interface PlanState {
  payload: UIPayload | null;
  setPayload: (payload: UIPayload | null) => void;
  markConfirmed: (item: UIItem) => void;
}

const PlanCtx = createContext<PlanState | null>(null);

/** Identity for a step. Steps have no server id, so the summary is the key. */
function keyOf(item: UIItem): string {
  return item.action?.display_summary ?? item.title;
}

export function PlanProvider({ children }: { children: React.ReactNode }) {
  const [payload, setPayload] = useState<UIPayload | null>(null);

  const markConfirmed = useCallback((target: UIItem) => {
    setPayload((current) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((item) =>
          keyOf(item) === keyOf(target) ? { ...item, status: 'confirmed' as const } : item,
        ),
      };
    });
  }, []);

  const value = useMemo(
    () => ({ payload, setPayload, markConfirmed }),
    [payload, markConfirmed],
  );
  return <PlanCtx.Provider value={value}>{children}</PlanCtx.Provider>;
}

export function usePlan(): PlanState {
  const ctx = useContext(PlanCtx);
  if (!ctx) throw new Error('usePlan must be used inside PlanProvider');
  return ctx;
}
