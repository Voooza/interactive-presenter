/**
 * Full-screen modal shown on narrow viewports instead of the inline
 * emoji reaction bar.
 *
 * Displays all allowed emojis in a grid, followed by optional poll and
 * question buttons. Closes on backdrop tap or Escape key. Calling any
 * action button also closes the modal after invoking the callback.
 */

import { useEffect } from 'react';

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

interface ReactionModalProps {
  onReact: (emoji: string) => void;
  onQuestionClick?: () => void;
  onPollClick?: () => void;
  hasPoll?: boolean;
  onClose: () => void;
}

export default function ReactionModal({
  onReact,
  onQuestionClick,
  onPollClick,
  hasPoll,
  onClose,
}: ReactionModalProps) {
  // Close on Escape.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleReact = (emoji: string) => {
    onReact(emoji);
    onClose();
  };

  const handlePollClick = () => {
    onPollClick?.();
    onClose();
  };

  const handleQuestionClick = () => {
    onQuestionClick?.();
    onClose();
  };

  return (
    <div
      className="reaction-modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-label="Emoji reactions"
      aria-modal="true"
    >
      <div
        className="reaction-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="reaction-modal-grid">
          {ALLOWED_EMOJIS.map((emoji) => (
            <button
              key={emoji}
              type="button"
              className="reaction-btn reaction-modal-btn"
              aria-label={`Send ${emoji} ${EMOJI_NAMES[emoji] ?? ''} reaction`}
              onClick={() => handleReact(emoji)}
            >
              {emoji}
            </button>
          ))}
        </div>

        {(onPollClick && hasPoll) || onQuestionClick ? (
          <div className="reaction-modal-actions">
            {onPollClick && hasPoll && (
              <button
                type="button"
                className="reaction-modal-action-btn"
                aria-label="Vote in poll"
                onClick={handlePollClick}
              >
                <span className="reaction-modal-action-icon">🗳️</span>
                Vote in poll
              </button>
            )}
            {onQuestionClick && (
              <button
                type="button"
                className="reaction-modal-action-btn"
                aria-label="Ask a question"
                onClick={handleQuestionClick}
              >
                <span className="reaction-modal-action-icon">❓</span>
                Ask a question
              </button>
            )}
          </div>
        ) : null}

        <button
          type="button"
          className="reaction-modal-close"
          aria-label="Close"
          onClick={onClose}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
