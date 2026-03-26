/**
 * Emoji reaction bar with responsive collapse behaviour.
 *
 * On wide viewports the component renders an inline pill-shaped bar with one
 * button per allowed emoji plus optional poll / question buttons.
 *
 * On narrow viewports — detected via a ResizeObserver watching the bar's own
 * rendered width — the bar collapses to a single trigger button (😊). Tapping
 * it opens a full-screen ReactionModal that shows all emojis in a grid. The
 * modal closes on tap-outside or Escape.
 *
 * The breakpoint is content-driven: the bar switches to collapsed mode
 * whenever it would be narrower than the natural width of all its buttons.
 * No pixel constants are hardcoded.
 *
 * Implementation note: the full bar is always rendered (just hidden via
 * aria-hidden + CSS visibility) so the ResizeObserver always has a live
 * element to measure. This lets the bar expand again when the viewport widens.
 */

import { useEffect, useRef, useState } from 'react';

import { ALLOWED_EMOJIS } from '../types';
import ReactionModal from './ReactionModal';

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

export default function EmojiReactionBar({
  onReact,
  onQuestionClick,
  onPollClick,
  hasPoll,
}: EmojiReactionBarProps) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  // ResizeObserver watches the outer (constrained) bar. Whenever it resizes
  // we compare the inner's natural scrollWidth against its constrained
  // clientWidth. If the content would overflow, we collapse.
  useEffect(() => {
    const outer = outerRef.current;
    const inner = innerRef.current;
    if (!outer || !inner) return;

    const check = () => {
      // scrollWidth reflects the content's natural width even with overflow:hidden.
      setCollapsed(inner.scrollWidth > inner.clientWidth);
    };

    const observer = new ResizeObserver(check);
    observer.observe(outer);
    // Run once synchronously after mount so the initial state is correct.
    check();
    return () => observer.disconnect();
  }, []);

  return (
    <>
      {/* The full bar is always in the DOM so the ResizeObserver can measure
          it. When collapsed we hide it visually and from assistive technology. */}
      <div
        ref={outerRef}
        className="reaction-bar"
        style={{ overflow: 'hidden', visibility: collapsed ? 'hidden' : undefined }}
        aria-hidden={collapsed ? 'true' : undefined}
      >
        <div ref={innerRef} className="reaction-bar-inner">
          {ALLOWED_EMOJIS.map((emoji) => (
            <button
              key={emoji}
              type="button"
              className="reaction-btn"
              aria-label={`Send ${emoji} ${EMOJI_NAMES[emoji] ?? ''} reaction`}
              onClick={() => onReact(emoji)}
              tabIndex={collapsed ? -1 : undefined}
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
              tabIndex={collapsed ? -1 : undefined}
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
              tabIndex={collapsed ? -1 : undefined}
            >
              ❓
            </button>
          )}
        </div>
      </div>

      {/* Collapsed trigger — shown only when the bar doesn't fit. */}
      {collapsed && (
        <button
          type="button"
          className="reaction-bar-trigger"
          aria-label="Open emoji reactions"
          onClick={() => setModalOpen(true)}
        >
          {/* Show burger menu icon when collapsed */}
          <span aria-hidden="true" style={{fontSize: '1.6em', display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32}}>
            {/* Accessible burger SVG instead of emoji */}
            <svg width="26" height="26" viewBox="0 0 26 26" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <rect y="5" width="26" height="3" rx="1.5" fill="currentColor"/>
              <rect y="11.5" width="26" height="3" rx="1.5" fill="currentColor"/>
              <rect y="18" width="26" height="3" rx="1.5" fill="currentColor"/>
            </svg>
          </span>
        </button>
      )}

      {/* Full-screen modal shown when the trigger is tapped. */}
      {modalOpen && (
        <ReactionModal
          onReact={onReact}
          onQuestionClick={onQuestionClick}
          onPollClick={onPollClick}
          hasPoll={hasPoll}
          onClose={() => setModalOpen(false)}
        />
      )}
    </>
  );
}
