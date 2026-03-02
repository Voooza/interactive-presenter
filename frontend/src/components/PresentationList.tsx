import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { fetchPresentations } from '../api';
import type { Presentation } from '../types';

export default function PresentationList() {
  const [presentations, setPresentations] = useState<Presentation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchPresentations()
      .then((data) => {
        if (!cancelled) {
          setPresentations(data);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          console.error('Failed to load presentations:', err);
          setError(message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="status-message">
        <p>Loading presentations…</p>
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

  if (presentations.length === 0) {
    return (
      <div className="status-message">
        <p>No presentations found.</p>
      </div>
    );
  }

  return (
    <main className="presentation-list">
      <h1>Presentations</h1>
      <ul>
        {presentations.map((p) => (
          <li key={p.id}>
            <Link to={`/presentations/${p.id}`}>{p.title}</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
