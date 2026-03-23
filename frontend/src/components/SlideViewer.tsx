import { useCallback, useEffect, useReducer, useState } from 'react';
import { useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { fetchSlides } from '../api';
import { usePolls } from '../hooks/usePolls';
import { useQuestions } from '../hooks/useQuestions';
import { useReactions } from '../hooks/useReactions';
import { useWebSocket } from '../hooks/useWebSocket';
import type { ServerMessage, Slide } from '../types';
import PollOverlay from './PollOverlay';
import { QRCodeOverlay } from './QRCodeOverlay';
import ReactionOverlay from './ReactionOverlay';

interface SlideState {
  slides: Slide[];
  currentIndex: number;
  loading: boolean;
  error: string | null;
}

type SlideAction =
  | { type: 'FETCH_START' }
  | { type: 'FETCH_SUCCESS'; slides: Slide[] }
  | { type: 'FETCH_ERROR'; message: string }
  | { type: 'NEXT' }
  | { type: 'PREV' };

const INITIAL_STATE: SlideState = {
  slides: [],
  currentIndex: 0,
  loading: true,
  error: null,
};

function slideReducer(state: SlideState, action: SlideAction): SlideState {
  switch (action.type) {
    case 'FETCH_START':
      return { slides: [], currentIndex: 0, loading: true, error: null };
    case 'FETCH_SUCCESS':
      return { ...state, slides: action.slides, loading: false };
    case 'FETCH_ERROR':
      return { ...state, loading: false, error: action.message };
    case 'NEXT':
      return { ...state, currentIndex: Math.min(state.currentIndex + 1, state.slides.length - 1) };
    case 'PREV':
      return { ...state, currentIndex: Math.max(state.currentIndex - 1, 0) };
    default:
      return state;
  }
}

export default function SlideViewer() {
  const { id } = useParams<{ id: string }>();
  const [{ slides, currentIndex, loading, error }, dispatch] = useReducer(
    slideReducer,
    INITIAL_STATE,
  );

  const [qaOpen, setQaOpen] = useState(false);

  const { activePoll, handleMessage: handlePollMessage } = usePolls();
  const { questions, handleMessage: handleQuestionMessage } = useQuestions();
  const { particles, addReaction } = useReactions();

  const handleMessage = useCallback(
    (msg: ServerMessage) => {
      handlePollMessage(msg);
      handleQuestionMessage(msg);
      if (msg.type === 'reaction_broadcast') {
        addReaction(msg.emoji);
      }
    },
    [handlePollMessage, handleQuestionMessage, addReaction],
  );

  const { isConnected, isReconnecting, audienceCount, send, reconnect } = useWebSocket({
    presentationId: id ?? '',
    role: 'presenter',
    onMessage: handleMessage,
  });

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    dispatch({ type: 'FETCH_START' });

    fetchSlides(id)
      .then((data) => {
        if (!cancelled) dispatch({ type: 'FETCH_SUCCESS', slides: data });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          console.error('Failed to load slides:', err);
          dispatch({ type: 'FETCH_ERROR', message });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  const goNext = useCallback(() => dispatch({ type: 'NEXT' }), []);
  const goPrev = useCallback(() => dispatch({ type: 'PREV' }), []);

  // Send navigate messages when slide index changes (after user navigates).
  const sendNavigate = useCallback(
    (slideIndex: number) => {
      send({
        type: 'navigate',
        timestamp: new Date().toISOString(),
        slide_index: slideIndex,
      });
    },
    [send],
  );

  // Send navigate message whenever currentIndex changes (and slides are loaded).
  useEffect(() => {
    if (slides.length > 0 && isConnected) {
      sendNavigate(currentIndex);
    }
  }, [currentIndex, slides.length, isConnected, sendNavigate]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') {
        e.preventDefault();
        goNext();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goPrev();
      } else if (e.key === 'q' || e.key === 'Q') {
        e.preventDefault();
        setQaOpen((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [goNext, goPrev]);

  if (loading) {
    return (
      <div className="status-message">
        <p>Loading slides…</p>
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

  const slide: Slide = slides[currentIndex];

  return (
    <div className="slide-viewer">
      <div className="slide-content">
        <h1 className="slide-title">{slide.title}</h1>
        {slide.content && (
          <div className="slide-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{slide.content}</ReactMarkdown>
          </div>
        )}
      </div>
      {currentIndex === 0 && id && (
        <QRCodeOverlay url={`${window.location.origin}/presentations/${id}/audience`} />
      )}
      {activePoll && activePoll.slideIndex === currentIndex && (
        <PollOverlay poll={activePoll} />
      )}
      {qaOpen && (
        <div className="qa-panel">
          <div className="qa-panel-header">
            <span>Questions ({questions.length})</span>
            <button
              type="button"
              className="qa-panel-close"
              onClick={() => setQaOpen(false)}
              aria-label="Close Q&A panel"
            >
              &times;
            </button>
          </div>
          <div className="qa-panel-body">
            {questions.length === 0 ? (
              <p className="qa-panel-empty">No questions yet.</p>
            ) : (
              <ul className="qa-question-list">
                {questions.map((q) => (
                  <li key={q.id} className="qa-question-item">
                    <span className="qa-question-slide-label">
                      Slide {q.slide_index + 1}
                    </span>
                    <p className="qa-question-text">{q.text}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      <ReactionOverlay particles={particles} />
      <div className="slide-footer">
        <div className="slide-counter" aria-label={`Slide ${currentIndex + 1} of ${slides.length}`}>
          {currentIndex + 1} / {slides.length}
        </div>
        <div className="ws-status">
          <button
            type="button"
            className="qa-badge"
            onClick={() => setQaOpen((prev) => !prev)}
            title="Toggle Q&A panel (Q)"
          >
            Q&amp;A
            {questions.length > 0 && (
              <span className="qa-badge-count">{questions.length}</span>
            )}
          </button>
          {isReconnecting && <span className="ws-dot ws-reconnecting" title="Reconnecting…" />}
          {!isConnected && !isReconnecting && (
            <span className="ws-disconnected">
              <span className="ws-dot ws-lost" title="Connection lost" />
              <button type="button" className="ws-reconnect-btn" onClick={reconnect}>
                Reconnect
              </button>
            </span>
          )}
          {isConnected && (
            <span className="ws-audience-count" title="Audience members connected">
              {audienceCount} viewer{audienceCount !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
