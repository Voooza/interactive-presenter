/** Domain types matching the backend API models. */

export interface Presentation {
  id: string;
  title: string;
}

export interface Slide {
  index: number;
  title: string;
  content: string;
}

// ---------------------------------------------------------------------------
// WebSocket message types
// ---------------------------------------------------------------------------

/** Server → Client: sent once after a successful handshake. */
export interface ConnectedMessage {
  type: 'connected';
  timestamp: string;
  role: 'presenter' | 'audience';
  presentation_id: string;
  current_slide: number;
  audience_count: number;
}

/** Server → Client: broadcast when the presenter navigates. */
export interface SlideChangedMessage {
  type: 'slide_changed';
  timestamp: string;
  slide_index: number;
}

/** Server → Client: broadcast when someone joins or leaves. */
export interface PeerCountMessage {
  type: 'peer_count';
  timestamp: string;
  audience_count: number;
  presenter_connected: boolean;
}

/** Server → Client: sent on validation failure. */
export interface ErrorMessage {
  type: 'error';
  timestamp: string;
  code: string;
  detail: string;
}

/** Server → Client: heartbeat response. */
export interface PongMessage {
  type: 'pong';
  timestamp: string;
}

/** Union of all server → client messages. */
export type ServerMessage =
  | ConnectedMessage
  | SlideChangedMessage
  | PeerCountMessage
  | ErrorMessage
  | PongMessage;

/** Client → Server: presenter requests a slide change. */
export interface NavigateMessage {
  type: 'navigate';
  timestamp: string;
  slide_index: number;
}

/** Client → Server: heartbeat ping. */
export interface PingMessage {
  type: 'ping';
  timestamp: string;
}

/** Union of all client → server messages. */
export type ClientMessage = NavigateMessage | PingMessage;
