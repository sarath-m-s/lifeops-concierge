export interface PendingAction {
  action_type: 'book_table' | 'place_food_order' | 'checkout_instamart';
  params: Record<string, any>;
  display_summary: string;
}

/**
 * A render instruction from the backend. The client maps `type` to a view and
 * hands it `props`. Unknown types are dropped rather than throwing, so the
 * backend can ship a new component before the app ships support for it.
 */
export interface Component {
  type: string;
  props: Record<string, any>;
}

/** One assistant turn: something to say, plus what to render alongside it. */
export interface AgentTurn {
  say: string;
  components: Component[];
}

export interface ConfirmResult {
  success: boolean;
  message: string;
  details?: Record<string, any>;
}

export interface AuthStatus {
  authenticated: boolean;
  expires_at?: number | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: Date;
  components?: Component[];
  /** Set when the turn failed, so the transcript shows it instead of going silent. */
  failed?: boolean;
}

/** A confirm_action the user has acted on, surfaced in the Plan tab. */
export interface TrackedAction {
  id: string;
  title: string;
  summary: string;
  total: string;
  source: 'food' | 'instamart' | 'dineout';
  status: 'pending' | 'confirmed' | 'failed';
  message?: string;
}
