import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';

import { fetchSlides } from '../api';
import { useWebSocket } from '../hooks/useWebSocket';
import type { Slide } from '../types';

/**
 * Audience companion page that follows the presenter's slide in real time.
 *
 * Connects as an audience member via WebSocket and updates the displayed
 * slide whenever the presenter navigates.
 */
export default function AudienceView() {
  const { id } = useParams<{ id: string }>();

  const [slides, setSlides] = useState<Slide[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { isConnected, isReconnecting, currentSlide, reconnect } = useWebSocket({
    presentationId: id ?? '',
    role: 'audience',
  });

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
      </div>
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
