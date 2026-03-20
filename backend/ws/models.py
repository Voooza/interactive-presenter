"""Pydantic models for WebSocket message validation."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# Client → Server messages
# ---------------------------------------------------------------------------


class NavigateMessage(BaseModel):
    """Presenter requests a slide change.

    Attributes:
        type: Always ``"navigate"``.
        timestamp: ISO 8601 UTC timestamp.
        slide_index: Zero-based target slide index.
    """

    type: str = Field("navigate", pattern="^navigate$")
    timestamp: str = Field(default_factory=_utc_now)
    slide_index: int


class PingMessage(BaseModel):
    """Client heartbeat ping.

    Attributes:
        type: Always ``"ping"``.
        timestamp: ISO 8601 UTC timestamp.
    """

    type: str = Field("ping", pattern="^ping$")
    timestamp: str = Field(default_factory=_utc_now)


# Allowed emoji set for reactions.
ALLOWED_EMOJIS: frozenset[str] = frozenset(
    {
        "👍",
        "👎",
        "❤️",
        "😂",
        "🎉",
        "🤔",
        "👏",
        "🔥",
        "😮",
        "🚀",
    }
)


class ReactionMessage(BaseModel):
    """Audience member sends an emoji reaction.

    Attributes:
        type: Always ``"reaction"``.
        timestamp: ISO 8601 UTC timestamp.
        emoji: A single emoji from the allowed set.
    """

    type: str = Field("reaction", pattern="^reaction$")
    timestamp: str = Field(default_factory=_utc_now)
    emoji: str


# ---------------------------------------------------------------------------
# Server → Client messages (constructed by server, not validated from input)
# ---------------------------------------------------------------------------


class ConnectedPayload(BaseModel):
    """Sent once after a successful WebSocket handshake.

    Attributes:
        type: Always ``"connected"``.
        timestamp: ISO 8601 UTC timestamp.
        role: The client's role (``"presenter"`` or ``"audience"``).
        presentation_id: The room's presentation identifier.
        current_slide: Zero-based active slide index.
        audience_count: Number of audience connections in the room.
    """

    type: str = "connected"
    timestamp: str = Field(default_factory=_utc_now)
    role: str
    presentation_id: str
    current_slide: int
    audience_count: int


class SlideChangedPayload(BaseModel):
    """Broadcast to audience when the presenter navigates.

    Attributes:
        type: Always ``"slide_changed"``.
        timestamp: ISO 8601 UTC timestamp.
        slide_index: Zero-based new slide index.
    """

    type: str = "slide_changed"
    timestamp: str = Field(default_factory=_utc_now)
    slide_index: int


class PeerCountPayload(BaseModel):
    """Broadcast when someone joins or leaves.

    Attributes:
        type: Always ``"peer_count"``.
        timestamp: ISO 8601 UTC timestamp.
        audience_count: Current number of audience connections.
        presenter_connected: Whether a presenter is connected.
    """

    type: str = "peer_count"
    timestamp: str = Field(default_factory=_utc_now)
    audience_count: int
    presenter_connected: bool


class ErrorPayload(BaseModel):
    """Sent to a single client on message validation failure.

    Attributes:
        type: Always ``"error"``.
        timestamp: ISO 8601 UTC timestamp.
        code: Machine-readable error code.
        detail: Human-readable description.
    """

    type: str = "error"
    timestamp: str = Field(default_factory=_utc_now)
    code: str
    detail: str


class PongPayload(BaseModel):
    """Server response to a client ping.

    Attributes:
        type: Always ``"pong"``.
        timestamp: ISO 8601 UTC timestamp.
    """

    type: str = "pong"
    timestamp: str = Field(default_factory=_utc_now)


class ReactionBroadcastPayload(BaseModel):
    """Broadcast to the presenter when an audience member reacts.

    Attributes:
        type: Always ``"reaction_broadcast"``.
        timestamp: ISO 8601 UTC timestamp.
        emoji: The emoji that was sent.
    """

    type: str = "reaction_broadcast"
    timestamp: str = Field(default_factory=_utc_now)
    emoji: str
