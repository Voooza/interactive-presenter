import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { fetchSlides } from '../api';
import { usePolls } from '../hooks/usePolls';
import { useQuestions } from '../hooks/useQuestions';
import { useWebSocket } from '../hooks/useWebSocket';
import type { ServerMessage, Slide } from '../types';
import EmojiReactionBar from './EmojiReactionBar';
import PollCard from './PollCard';
import QuestionModal from './QuestionModal';

/**
 * Audience companion page that follows the presenter's slide in real time.
 *
 * Connects as an audience member via WebSocket and updates the displayed
 * slide whenever the presenter navigates. Shows poll vote buttons when
 * the current slide contains a poll, and a question-mark button in the
 * emoji bar that opens a modal for Q&A submission.
 */
export default function AudienceView() {
  const { id } = useParams<{ id: string }>();

  const [slides, setSlides] = useState<Slide[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [questionModalOpen, setQuestionModalOpen] = useState(false);
  const [modalKey, setModalKey] = useState(0);
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

  const handleQuestionSubmit = (text: string) => {
    send({
      type: 'question_submit',
      timestamp: new Date().toISOString(),
      text,
    });
    setSubmitting(true);
  };

  // Clear the submitting flag when the server confirms receipt.
  // This pattern matches the original code and the lint warning is pre-existing.
  if (lastConfirmed && submitting) {
    setSubmitting(false);
  }

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
        <p>Loading presentation...</p>
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

  return (
    <div className="slide-viewer audience-view">
      {isReconnecting && (
        <div className="ws-banner ws-banner-reconnecting">Reconnecting...</div>
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
        {activePoll && activePoll.slideIndex === slideIndex ? (
          <>
            {slide.content && (
              <div className="slide-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{slide.content}</ReactMarkdown>
              </div>
            )}
            <PollCard poll={activePoll} onVote={handleVote} />
          </>
        ) : (
          slide.content && (
            <div className="slide-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{slide.content}</ReactMarkdown>
            </div>
          )
        )}
      </div>

      <EmojiReactionBar
        onReact={handleReact}
        onQuestionClick={() => {
          setModalKey((k) => k + 1);
          setQuestionModalOpen(true);
        }}
      />

      {questionModalOpen && (
        <QuestionModal
          key={modalKey}
          disabled={!isConnected}
          submitting={submitting}
          lastConfirmed={lastConfirmed}
          onSubmit={handleQuestionSubmit}
          onClose={() => setQuestionModalOpen(false)}
        />
      )}

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
