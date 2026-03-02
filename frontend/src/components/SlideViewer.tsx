import { useCallback, useEffect, useReducer } from 'react';
import { useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';

import { fetchSlides } from '../api';
import type { Slide } from '../types';

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

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') {
        e.preventDefault();
        goNext();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goPrev();
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
            <ReactMarkdown>{slide.content}</ReactMarkdown>
          </div>
        )}
      </div>
      <div className="slide-counter" aria-label={`Slide ${currentIndex + 1} of ${slides.length}`}>
        {currentIndex + 1} / {slides.length}
      </div>
    </div>
  );
}
