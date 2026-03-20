"""Per-connection sliding-window rate limiter."""

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _WindowConfig:
    """Configuration for a rate limit window.

    Attributes:
        limit: Maximum number of messages allowed in the window.
        window_seconds: Window duration in seconds.
    """

    limit: int
    window_seconds: float


# Default rate limits per message category.
_LIMITS: dict[str, _WindowConfig] = {
    "reaction": _WindowConfig(limit=5, window_seconds=3.0),
    "poll_vote": _WindowConfig(limit=1, window_seconds=1e9),  # 1 ever (approximated)
    "question_submit": _WindowConfig(limit=3, window_seconds=60.0),
    "navigate": _WindowConfig(limit=20, window_seconds=10.0),
}

_DEFAULT_LIMIT = _WindowConfig(limit=30, window_seconds=10.0)


@dataclass
class RateLimiter:
    """Sliding-window rate limiter for a single WebSocket connection.

    Each instance tracks message timestamps per category and enforces the
    configured limits.

    Attributes:
        _timestamps: Mapping from message category to list of timestamps.
    """

    _timestamps: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def check(self, message_type: str) -> bool:
        """Return ``True`` if the message is allowed, ``False`` if rate-limited.

        Args:
            message_type: The ``type`` field of the incoming message.

        Returns:
            Whether the message should be processed.
        """
        config = _LIMITS.get(message_type, _DEFAULT_LIMIT)
        now = time.monotonic()
        cutoff = now - config.window_seconds

        timestamps = self._timestamps[message_type]
        # Prune expired entries.
        self._timestamps[message_type] = [t for t in timestamps if t > cutoff]
        timestamps = self._timestamps[message_type]

        if len(timestamps) >= config.limit:
            return False

        timestamps.append(now)
        return True
