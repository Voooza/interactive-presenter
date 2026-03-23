/**
 * Modal overlay for submitting audience questions.
 *
 * Opened from the question button in the emoji reaction bar. Contains a
 * text input, character counter, and submit button. Closes on successful
 * submission, backdrop click, or Escape key.
 *
 * The parent controls mount/unmount via the `open` prop. When mounted,
 * the component initialises with empty text. The parent passes a `key`
 * prop that changes each time the modal opens so React resets all
 * internal state automatically.
 */

import { useEffect, useRef, useState } from 'react';

import type { QuestionData } from '../types';

const MAX_QUESTION_LENGTH = 280;

interface QuestionModalProps {
  disabled: boolean;
  submitting: boolean;
  lastConfirmed: QuestionData | null;
  onSubmit: (text: string) => void;
  onClose: () => void;
}

export default function QuestionModal({
  disabled,
  submitting,
  lastConfirmed,
  onSubmit,
  onClose,
}: QuestionModalProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [initialConfirmed] = useState(lastConfirmed);

  const charsRemaining = MAX_QUESTION_LENGTH - text.length;
  const canSubmit =
    text.trim().length > 0 && text.length <= MAX_QUESTION_LENGTH && !submitting;

  // Show confirmation when a new lastConfirmed appears after mount.
  const showConfirmation =
    lastConfirmed !== null && lastConfirmed !== initialConfirmed;

  // Focus textarea on mount.
  useEffect(() => {
    const timer = setTimeout(() => textareaRef.current?.focus(), 50);
    return () => clearTimeout(timer);
  }, []);

  // Close on Escape.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Auto-close after confirmation is shown briefly.
  useEffect(() => {
    if (showConfirmation) {
      const timer = setTimeout(() => onClose(), 1200);
      return () => clearTimeout(timer);
    }
  }, [showConfirmation, onClose]);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (trimmed.length === 0 || trimmed.length > MAX_QUESTION_LENGTH) return;
    onSubmit(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (canSubmit && !disabled) {
        handleSubmit();
      }
    }
  };

  return (
    <div className="question-modal-backdrop" onClick={onClose}>
      <div
        className="question-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Ask a question"
        aria-modal="true"
      >
        <textarea
          ref={textareaRef}
          className="qa-textarea"
          placeholder="Ask a question..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          maxLength={MAX_QUESTION_LENGTH}
          rows={3}
          disabled={disabled || submitting}
        />
        <div className="qa-form-footer">
          <span
            className={`qa-char-counter${charsRemaining < 0 ? ' qa-char-over' : charsRemaining <= 30 ? ' qa-char-warn' : ''}`}
          >
            {charsRemaining}
          </span>
          <div className="question-modal-actions">
            <button
              type="button"
              className="question-modal-cancel"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="button"
              className="qa-submit-btn"
              disabled={!canSubmit || disabled}
              onClick={handleSubmit}
            >
              {submitting ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>
        {showConfirmation && (
          <p className="qa-confirmation">Question submitted!</p>
        )}
      </div>
    </div>
  );
}
