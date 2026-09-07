export interface PendingAction {
  action_type: 'book_table' | 'place_food_order' | 'checkout_instamart';
  params: Record<string, any>;
  display_summary: string;
}

export interface UIItem {
  id?: string;
  step?: number;
  icon?: string;
  category?: string;
  title: string;
  subtitle?: string;
  time?: string;
  details: Record<string, string>;
  status: 'pending' | 'ready' | 'confirmed' | 'failed';
  source: 'dineout' | 'food' | 'instamart';
  powered_by?: string;
  action?: PendingAction;
}

export interface UIPayload {
  type: 'timeline' | 'cards' | 'cart' | 'status' | 'confirmation';
  items: UIItem[];
  title?: string;
}

export interface AgentResponse {
  spoken_response: string;
  ui_payload: UIPayload;
  requires_confirmation: boolean;
  pending_action: PendingAction | null;
}

export interface ConfirmResult {
  success: boolean;
  message: string;
  details?: Record<string, any>;
}

export interface AuthStatus {
  authenticated: boolean;
  mock_mode: boolean;
  expires_at?: number | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: Date;
  spoken?: boolean;
  payload?: UIPayload;
}
