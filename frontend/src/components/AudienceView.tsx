import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';

import { fetchSlides } from '../api';
import { usePolls } from '../hooks/usePolls';
import { useQuestions } from '../hooks/useQuestions';
import { useWebSocket } from '../hooks/useWebSocket';
import type { ServerMessage, Slide } from '../types';
import EmojiReactionBar from './EmojiReactionBar';
import PollCard from './PollCard';

const MAX_QUESTION_LENGTH = 280;

/**
 * Audience companion page that follows the presenter's slide in real time.
 *
 * Connects as an audience member via WebSocket and updates the displayed
 * slide whenever the presenter navigates. Shows poll vote buttons when
 * the current slide contains a poll, and a question submission form for Q&A.
 */
export default function AudienceView() {
  const { id } = useParams<{ id: string }>();

  const [slides, setSlides] = useState<Slide[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [questionText, setQuestionText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const { activePoll, markVoted, handleMessage: handlePollMessage } = usePolls();
  const { lastConfirmed, handleMessage: handleQuestionMessage } = useQuestions();

  const handleMessage = useCallback(
    (message: ServerMessage) => {
      handlePollMessage(message);
      handleQuestionMessage(message);
    },
    [handlePollMessage, handleQuestionMessage],
  );

  const { isConnected, isReconnecting, currentSlide, send, reconnect } = useWebSocket({
    presentationId: id ?? '',
    role: 'audience',
    onMessage: handleMessage,
  });

  const handleVote = (slideIndex: number, optionIndex: number) => {
    send({
      type: 'poll_vote',
      timestamp: new Date().toISOString(),
      slide_index: slideIndex,
      option_index: optionIndex,
    });
    markVoted(slideIndex, optionIndex);
  };

  const handleReact = (emoji: string) => {
    send({
      type: 'reaction',
      timestamp: new Date().toISOString(),
      emoji,
    });
  };

  const handleQuestionSubmit = () => {
    const trimmed = questionText.trim();
    if (trimmed.length === 0 || trimmed.length > MAX_QUESTION_LENGTH) return;
    send({
      type: 'question_submit',
      timestamp: new Date().toISOString(),
      text: trimmed,
    });
    setSubmitting(true);
    setQuestionText('');
  };

  // Clear the submitting state once the server confirms receipt.
  useEffect(() => {
    if (lastConfirmed) {
      setSubmitting(false);
    }
  }, [lastConfirmed]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    fetchSlides(id)
      .then((data) => {
        if (!cancelled) {
          setSlides(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          console.error('Failed to load slides:', err);
          setError(message);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="status-message">
        <p>Loading presentation…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="status-message error">
        <p>Error: {error}</p>
      </div>
    );
  }

  if (slides.length === 0) {
    return (
      <div className="status-message">
        <p>No slides found.</p>
      </div>
    );
  }

  const slideIndex = Math.min(currentSlide, slides.length - 1);
  const slide = slides[slideIndex];

  const charsRemaining = MAX_QUESTION_LENGTH - questionText.length;
  const canSubmit =
    questionText.trim().length > 0 && questionText.length <= MAX_QUESTION_LENGTH && !submitting;

  return (
    <div className="slide-viewer audience-view">
      {isReconnecting && (
        <div className="ws-banner ws-banner-reconnecting">Reconnecting…</div>
      )}
      {!isConnected && !isReconnecting && (
        <div className="ws-banner ws-banner-lost">
          Connection lost.{' '}
          <button type="button" className="ws-reconnect-btn" onClick={reconnect}>
            Reconnect
          </button>
        </div>
      )}

      <div className="slide-content">
        <h1 className="slide-title">{slide.title}</h1>
        {slide.content && (
          <div className="slide-body">
            <ReactMarkdown>{slide.content}</ReactMarkdown>
          </div>
        )}
        {activePoll && activePoll.slideIndex === slideIndex && (
          <PollCard poll={activePoll} onVote={handleVote} />
        )}
      </div>

      <div className="qa-form">
        <textarea
          className="qa-textarea"
          placeholder="Ask a question…"
          value={questionText}
          onChange={(e) => setQuestionText(e.target.value)}
          maxLength={MAX_QUESTION_LENGTH}
          rows={2}
          disabled={!isConnected || submitting}
        />
        <div className="qa-form-footer">
          <span
            className={`qa-char-counter${charsRemaining < 0 ? ' qa-char-over' : charsRemaining <= 30 ? ' qa-char-warn' : ''}`}
          >
            {charsRemaining}
          </span>
          <button
            type="button"
            className="qa-submit-btn"
            disabled={!canSubmit || !isConnected}
            onClick={handleQuestionSubmit}
          >
            {submitting ? 'Sending…' : 'Send'}
          </button>
        </div>
        {lastConfirmed && (
          <p className="qa-confirmation">Question submitted!</p>
        )}
      </div>

      <EmojiReactionBar onReact={handleReact} />
      <div className="slide-footer">
        <div
          className="slide-counter"
          aria-label={`Slide ${slideIndex + 1} of ${slides.length}`}
        >
          {slideIndex + 1} / {slides.length}
        </div>
      </div>
    </div>
  );
}
