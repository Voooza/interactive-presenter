/** Domain types matching the backend API models. */

export interface Presentation {
  id: string;
  title: string;
}

export interface Slide {
  index: number;
  title: string;
  content: string;
  poll_options: string[];
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

/** Server → Client: broadcast when a poll slide is navigated to. */
export interface PollOpenedMessage {
  type: 'poll_opened';
  timestamp: string;
  slide_index: number;
  options: string[];
  results: number[];
}

/** Server → Client: broadcast when poll votes are updated. */
export interface PollResultsMessage {
  type: 'poll_results';
  timestamp: string;
  slide_index: number;
  options: string[];
  results: number[];
}

/** Server → Client: broadcast when the presenter navigates away from a poll slide. */
export interface PollClosedMessage {
  type: 'poll_closed';
  timestamp: string;
  slide_index: number;
  options: string[];
  results: number[];
}

/** Server → Client: broadcast when an audience member sends an emoji reaction. */
export interface ReactionBroadcastMessage {
  type: 'reaction_broadcast';
  timestamp: string;
  emoji: string;
}

/** Union of all server → client messages. */
export type ServerMessage =
  | ConnectedMessage
  | SlideChangedMessage
  | PeerCountMessage
  | ErrorMessage
  | PongMessage
  | PollOpenedMessage
  | PollResultsMessage
  | PollClosedMessage
  | ReactionBroadcastMessage;

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

/** Client → Server: audience member casts a poll vote. */
export interface PollVoteMessage {
  type: 'poll_vote';
  timestamp: string;
  slide_index: number;
  option_index: number;
}

/** Client → Server: audience member sends an emoji reaction. */
export interface ReactionMessage {
  type: 'reaction';
  timestamp: string;
  emoji: string;
}

/** Union of all client → server messages. */
export type ClientMessage = NavigateMessage | PingMessage | PollVoteMessage | ReactionMessage;

// ---------------------------------------------------------------------------
// Emoji reactions — allowed set
// ---------------------------------------------------------------------------

/** The fixed, curated set of 10 emojis for v1 reactions. */
export const ALLOWED_EMOJIS: readonly string[] = [
  '\u{1F44D}', // 👍 thumbs-up
  '\u{1F44F}', // 👏 clapping
  '\u{2764}\u{FE0F}', // ❤️ heart
  '\u{1F602}', // 😂 laughing
  '\u{1F62E}', // 😮 surprised
  '\u{1F525}', // 🔥 fire
  '\u{1F389}', // 🎉 party
  '\u{1F914}', // 🤔 thinking
  '\u{1F4AF}', // 💯 hundred
  '\u{1F440}', // 👀 eyes
] as const;
