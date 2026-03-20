import type { PollState } from '../hooks/usePolls';

/**
 * Poll overlay displayed on the presenter's slide viewer.
 *
 * Shows a live bar chart of poll results so the presenter can see how
 * the audience is voting in real time.
 */
export default function PollOverlay({ poll }: { poll: PollState }) {
  const totalVotes = poll.results.reduce((a, b) => a + b, 0);

  return (
    <div className="poll-overlay">
      <div className="poll-overlay-header">
        Poll Results {!poll.isOpen && <span className="poll-closed-badge">Closed</span>}
      </div>
      <div className="poll-results">
        {poll.options.map((option, i) => {
          const pct = totalVotes > 0 ? (poll.results[i] / totalVotes) * 100 : 0;
          return (
            <div key={i} className="poll-result-row">
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
      </div>
    </div>
  );
}
