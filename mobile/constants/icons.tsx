/**
 * Icon vocabulary. The backend sends data (`source`, `category`) and the client
 * decides how to draw it — no glyphs cross the wire.
 */
import React from 'react';
import {
  AlertCircle,
  Check,
  ChevronRight,
  CircleSlash,
  Clock,
  Link2,
  LucideIcon,
  MessageSquare,
  Send,
  Settings,
  ShieldCheck,
  ShoppingBasket,
  Sparkles,
  UtensilsCrossed,
  Bike,
  ListChecks,
  RefreshCw,
  Trash2,
  Volume2,
} from 'lucide-react-native';

/** Which icon represents a plan step. Category wins; service is the fallback. */
export function stepIcon(category?: string, source?: string): LucideIcon {
  switch (category) {
    case 'dinner':
      return UtensilsCrossed;
    case 'delivery':
      return Bike;
    case 'grocery':
      return ShoppingBasket;
  }
  switch (source) {
    case 'dineout':
      return UtensilsCrossed;
    case 'food':
      return Bike;
    case 'instamart':
      return ShoppingBasket;
    default:
      return Sparkles;
  }
}

export const Icons = {
  chat: MessageSquare,
  plan: ListChecks,
  settings: Settings,
  send: Send,
  clock: Clock,
  check: Check,
  chevron: ChevronRight,
  error: AlertCircle,
  empty: CircleSlash,
  connect: Link2,
  shield: ShieldCheck,
  refresh: RefreshCw,
  trash: Trash2,
  speaker: Volume2,
  spark: Sparkles,
};

export type { LucideIcon };
export { React };
