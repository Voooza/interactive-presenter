/**
 * Purely presentational component that renders the emoji reaction picker bar.
 *
 * Displays one button per allowed emoji followed by an optional question
 * button separated by a divider. Calls `onReact` with the emoji character
 * when a reaction button is tapped and `onQuestionClick` when the question
 * button is tapped. Has no internal state or WebSocket awareness — rate
 * limiting is enforced server-side.
 */

import { ALLOWED_EMOJIS } from '../types';

/** Human-readable names for each emoji, used as accessible aria-labels. */
const EMOJI_NAMES: Record<string, string> = {
  '👍': 'thumbs-up',
  '👏': 'clapping',
  '❤️': 'heart',
  '😂': 'laughing',
  '😮': 'surprised',
  '🔥': 'fire',
  '🎉': 'party',
  '🤔': 'thinking',
  '💯': 'hundred',
  '👀': 'eyes',
};

interface EmojiReactionBarProps {
  onReact: (emoji: string) => void;
  onQuestionClick?: () => void;
  onPollClick?: () => void;
  hasPoll?: boolean;
}

export default function EmojiReactionBar({ onReact, onQuestionClick, onPollClick, hasPoll }: EmojiReactionBarProps) {
  return (
    <div className="reaction-bar">
      {ALLOWED_EMOJIS.map((emoji) => (
        <button
          key={emoji}
          type="button"
          className="reaction-btn"
          aria-label={`Send ${emoji} ${EMOJI_NAMES[emoji] ?? ''} reaction`}
          onClick={() => onReact(emoji)}
        >
          {emoji}
        </button>
      ))}
      {(onQuestionClick || (onPollClick && hasPoll)) && (
        <div className="reaction-bar-divider" aria-hidden="true" />
      )}
      {onPollClick && hasPoll && (
        <button
          type="button"
          className="reaction-btn reaction-btn-poll"
          aria-label="Vote in poll"
          onClick={onPollClick}
        >
          🗳️
        </button>
      )}
      {onQuestionClick && (
        <button
          type="button"
          className="reaction-btn reaction-btn-question"
          aria-label="Ask a question"
          onClick={onQuestionClick}
        >
          ❓
        </button>
      )}
    </div>
  );
}
