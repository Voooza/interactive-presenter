/**
 * Modal overlay for audience poll voting.
 *
 * Opened from the poll button in the emoji reaction bar. Shows vote
 * buttons when the poll is open, or a results bar chart after voting.
 * Closes on backdrop click or Escape key.
 */

import { useEffect } from 'react';

import type { PollState } from '../hooks/usePolls';

interface PollModalProps {
  poll: PollState;
  onVote: (slideIndex: number, optionIndex: number) => void;
  onClose: () => void;
}

export default function PollModal({ poll, onVote, onClose }: PollModalProps) {
  const totalVotes = poll.results.reduce((a, b) => a + b, 0);
  const showResults = poll.hasVoted || !poll.isOpen;

  // Close on Escape.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="question-modal-backdrop" onClick={onClose}>
      <div
        className="question-modal poll-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Vote in poll"
        aria-modal="true"
      >
        {!showResults ? (
          <div className="poll-options">
            {poll.options.map((option, i) => (
              <button
                key={i}
                type="button"
                className="poll-option-btn"
                onClick={() => onVote(poll.slideIndex, i)}
              >
                {option}
              </button>
            ))}
          </div>
        ) : (
          <div className="poll-results">
            {poll.options.map((option, i) => {
              const pct = totalVotes > 0 ? (poll.results[i] / totalVotes) * 100 : 0;
              const isVoted = poll.votedOption === i;
              return (
                <div key={i} className={`poll-result-row${isVoted ? ' poll-result-voted' : ''}`}>
                  <div className="poll-result-label">
                    <span className="poll-result-option">{option}</span>
                    <span className="poll-result-count">
                      {poll.results[i]} ({Math.round(pct)}%)
                    </span>
                  </div>
                  <div className="poll-result-bar-bg">
                    <div
                      className="poll-result-bar-fill"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
            <div className="poll-total-votes">{totalVotes} vote{totalVotes !== 1 ? 's' : ''}</div>
            <button
              type="button"
              className="question-modal-cancel poll-modal-close"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
