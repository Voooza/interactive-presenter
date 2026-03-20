import type { PollState } from '../hooks/usePolls';

/**
 * Poll card displayed on the audience view.
 *
 * Shows vote buttons when the poll is open and the user hasn't voted.
 * After voting (or when closed), shows a horizontal bar chart of results.
 */
export default function PollCard({
  poll,
  onVote,
}: {
  poll: PollState;
  onVote: (slideIndex: number, optionIndex: number) => void;
}) {
  const totalVotes = poll.results.reduce((a, b) => a + b, 0);
  const showResults = poll.hasVoted || !poll.isOpen;

  return (
    <div className="poll-card">
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
        </div>
      )}
    </div>
  );
}
