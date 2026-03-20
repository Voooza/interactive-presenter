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


class PollVoteMessage(BaseModel):
    """Audience member casts a poll vote.

    Attributes:
        type: Always ``"poll_vote"``.
        timestamp: ISO 8601 UTC timestamp.
        slide_index: The poll slide being voted on.
        option_index: Zero-based index of the chosen option.
    """

    type: str = Field("poll_vote", pattern="^poll_vote$")
    timestamp: str = Field(default_factory=_utc_now)
    slide_index: int
    option_index: int


class QuestionSubmitMessage(BaseModel):
    """Audience member submits a question.

    Attributes:
        type: Always ``"question_submit"``.
        timestamp: ISO 8601 UTC timestamp.
        text: The question text (1–280 characters).
    """

    type: str = Field("question_submit", pattern="^question_submit$")
    timestamp: str = Field(default_factory=_utc_now)
    text: str


class GetQuestionsMessage(BaseModel):
    """Presenter requests the current list of questions.

    Attributes:
        type: Always ``"get_questions"``.
        timestamp: ISO 8601 UTC timestamp.
    """

    type: str = Field("get_questions", pattern="^get_questions$")
    timestamp: str = Field(default_factory=_utc_now)


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


class PollOpenedPayload(BaseModel):
    """Sent to all clients when the presenter navigates to a poll slide.

    Attributes:
        type: Always ``"poll_opened"``.
        timestamp: ISO 8601 UTC timestamp.
        slide_index: The slide that contains the poll.
        options: List of poll option strings.
        results: Current vote counts per option.
    """

    type: str = "poll_opened"
    timestamp: str = Field(default_factory=_utc_now)
    slide_index: int
    options: list[str]
    results: list[int]


class PollResultsPayload(BaseModel):
    """Broadcast to all clients when poll votes are updated.

    Attributes:
        type: Always ``"poll_results"``.
        timestamp: ISO 8601 UTC timestamp.
        slide_index: The slide that contains the poll.
        options: List of poll option strings.
        results: Current vote counts per option.
    """

    type: str = "poll_results"
    timestamp: str = Field(default_factory=_utc_now)
    slide_index: int
    options: list[str]
    results: list[int]


class PollClosedPayload(BaseModel):
    """Sent to all clients when the presenter navigates away from a poll slide.

    Attributes:
        type: Always ``"poll_closed"``.
        timestamp: ISO 8601 UTC timestamp.
        slide_index: The slide whose poll is closed.
        options: List of poll option strings.
        results: Final vote counts per option.
    """

    type: str = "poll_closed"
    timestamp: str = Field(default_factory=_utc_now)
    slide_index: int
    options: list[str]
    results: list[int]


# ---------------------------------------------------------------------------
# Q&A payloads
# ---------------------------------------------------------------------------


class QuestionData(BaseModel):
    """A single audience question.

    Attributes:
        id: Unique sequential identifier within the room.
        text: The question text.
        slide_index: Zero-based slide index when the question was submitted.
        timestamp: ISO 8601 UTC timestamp when the question was submitted.
    """

    id: int
    text: str
    slide_index: int
    timestamp: str


class QuestionReceivedPayload(BaseModel):
    """Sent to the submitting audience member to confirm receipt.

    Attributes:
        type: Always ``"question_received"``.
        timestamp: ISO 8601 UTC timestamp.
        question: The question that was received.
    """

    type: str = "question_received"
    timestamp: str = Field(default_factory=_utc_now)
    question: QuestionData


class QuestionsListPayload(BaseModel):
    """Sent to the presenter with the full list of questions.

    Attributes:
        type: Always ``"questions_list"``.
        timestamp: ISO 8601 UTC timestamp.
        questions: All questions submitted so far.
    """

    type: str = "questions_list"
    timestamp: str = Field(default_factory=_utc_now)
    questions: list[QuestionData]


class QuestionNotifyPayload(BaseModel):
    """Sent to the presenter when a new question arrives.

    Attributes:
        type: Always ``"question_notify"``.
        timestamp: ISO 8601 UTC timestamp.
        question: The newly submitted question.
    """

    type: str = "question_notify"
    timestamp: str = Field(default_factory=_utc_now)
    question: QuestionData
