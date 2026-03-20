"""Room and WebSocket connection tracking."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

from fastapi import WebSocket

from backend.ws.models import (
    ConnectedPayload,
    PeerCountPayload,
    QuestionData,
    QuestionsListPayload,
)

logger = logging.getLogger(__name__)

_GRACE_PERIOD_DEFAULT = 30


def _grace_period_seconds() -> float:
    """Return the configured room grace period in seconds."""
    return float(
        os.environ.get("WS_ROOM_GRACE_PERIOD_SECONDS", str(_GRACE_PERIOD_DEFAULT))
    )


@dataclass(eq=False)
class _Connection:
    """A single WebSocket connection with metadata.

    Uses identity-based equality so instances can be stored in sets.

    Attributes:
        websocket: The underlying FastAPI WebSocket.
        role: ``"presenter"`` or ``"audience"``.
        presentation_id: The room this connection belongs to.
        last_message_at: Monotonic timestamp of the last received message.
    """

    websocket: WebSocket
    role: str
    presentation_id: str
    last_message_at: float = field(default_factory=time.monotonic)


@dataclass
class _PollState:
    """In-memory poll state for a single slide.

    Attributes:
        slide_index: The slide this poll belongs to.
        options: List of poll option strings.
        votes: Vote counts per option (parallel to ``options``).
        voters: Set of connection ids that have already voted.
    """

    slide_index: int
    options: list[str]
    votes: list[int] = field(default_factory=list)
    voters: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Initialise vote counts if not already set."""
        if not self.votes:
            self.votes = [0] * len(self.options)


@dataclass
class _Room:
    """A logical grouping of connections for a single presentation.

    Attributes:
        presentation_id: Room identifier matching the REST API.
        current_slide: Zero-based active slide index.
        presenter: The presenter connection, if any.
        audience: Set of audience connections.
        created_at: Monotonic timestamp when the room was created.
        grace_task: Handle for the grace-period cleanup task.
        polls: Poll state keyed by slide index.
        active_poll: Slide index of the currently active poll, if any.
        questions: Ordered list of audience questions.
        _next_question_id: Auto-incrementing counter for question IDs.
    """

    presentation_id: str
    current_slide: int = 0
    presenter: _Connection | None = None
    audience: set[_Connection] = field(default_factory=set)
    created_at: float = field(default_factory=time.monotonic)
    grace_task: asyncio.Task[None] | None = None
    polls: dict[int, _PollState] = field(default_factory=dict)
    active_poll: int | None = None
    questions: list[QuestionData] = field(default_factory=list)
    _next_question_id: int = 0

    @property
    def audience_count(self) -> int:
        """Return the number of audience connections."""
        return len(self.audience)

    @property
    def presenter_connected(self) -> bool:
        """Return whether a presenter is currently connected."""
        return self.presenter is not None

    @property
    def is_empty(self) -> bool:
        """Return whether the room has no connections."""
        return self.presenter is None and len(self.audience) == 0


class ConnectionManager:
    """Manages WebSocket rooms and connections.

    A single instance is created at app startup and attached to
    ``app.state.connection_manager``.

    Attributes:
        rooms: Active rooms keyed by ``presentation_id``.
        _connections: Mapping from WebSocket to its ``_Connection`` wrapper.
    """

    def __init__(self) -> None:
        self.rooms: dict[str, _Room] = {}
        self._connections: dict[WebSocket, _Connection] = {}

    async def connect(
        self, websocket: WebSocket, presentation_id: str, role: str
    ) -> _Connection:
        """Add a WebSocket to the appropriate room.

        Creates the room if it does not exist. If a grace-period timer is
        running for the room, it is cancelled.

        Args:
            websocket: The FastAPI WebSocket instance.
            presentation_id: Which presentation to join.
            role: ``"presenter"`` or ``"audience"``.

        Returns:
            The ``_Connection`` wrapper for the new connection.

        Raises:
            ValueError: If the room already has a presenter and ``role``
                is ``"presenter"``.
        """
        room = self.rooms.get(presentation_id)
        if room is None:
            room = _Room(presentation_id=presentation_id)
            self.rooms[presentation_id] = room
        elif room.grace_task is not None:
            room.grace_task.cancel()
            room.grace_task = None

        conn = _Connection(
            websocket=websocket,
            role=role,
            presentation_id=presentation_id,
        )

        if role == "presenter":
            if room.presenter is not None:
                raise ValueError("Presenter slot already taken")
            room.presenter = conn
        else:
            room.audience.add(conn)

        self._connections[websocket] = conn

        # Send connected payload to the new client.
        connected = ConnectedPayload(
            role=role,
            presentation_id=presentation_id,
            current_slide=room.current_slide,
            audience_count=room.audience_count,
        )
        await websocket.send_json(connected.model_dump())

        # Auto-send questions list to presenter on connect (always, even when empty).
        if role == "presenter":
            ql = QuestionsListPayload(questions=list(room.questions))
            await websocket.send_json(ql.model_dump())

        # Broadcast updated peer count.
        await self._broadcast_peer_count(room)

        return conn

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from its room.

        Broadcasts an updated peer count to remaining connections. If the
        room becomes empty, starts the grace-period timer.

        Args:
            websocket: The WebSocket to remove.
        """
        conn = self._connections.pop(websocket, None)
        if conn is None:
            return

        room = self.rooms.get(conn.presentation_id)
        if room is None:
            return

        if conn.role == "presenter" and room.presenter is conn:
            room.presenter = None
        else:
            room.audience.discard(conn)

        # Broadcast updated peer count to remaining connections.
        if not room.is_empty:
            await self._broadcast_peer_count(room)

        # Start grace period if room is empty.
        if room.is_empty:
            room.grace_task = asyncio.create_task(
                self._grace_period_cleanup(conn.presentation_id)
            )

    async def broadcast_to_room(
        self, presentation_id: str, message: dict[str, object]
    ) -> None:
        """Send a message to every connection in a room.

        Args:
            presentation_id: Target room.
            message: JSON-serialisable dict to send.
        """
        room = self.rooms.get(presentation_id)
        if room is None:
            return

        tasks: list[asyncio.Task[None]] = []
        if room.presenter is not None:
            tasks.append(
                asyncio.create_task(room.presenter.websocket.send_json(message))
            )
        for conn in list(room.audience):
            tasks.append(asyncio.create_task(conn.websocket.send_json(message)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send_to_presenter(
        self, presentation_id: str, message: dict[str, object]
    ) -> None:
        """Send a message to the room's presenter only.

        Args:
            presentation_id: Target room.
            message: JSON-serialisable dict to send.
        """
        room = self.rooms.get(presentation_id)
        if room is None or room.presenter is None:
            return
        await room.presenter.websocket.send_json(message)

    async def send_to_audience(
        self, presentation_id: str, message: dict[str, object]
    ) -> None:
        """Send a message to all audience members in a room.

        Args:
            presentation_id: Target room.
            message: JSON-serialisable dict to send.
        """
        room = self.rooms.get(presentation_id)
        if room is None:
            return
        tasks = [
            asyncio.create_task(conn.websocket.send_json(message))
            for conn in list(room.audience)
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_connection(self, websocket: WebSocket) -> _Connection | None:
        """Look up the ``_Connection`` wrapper for a WebSocket.

        Args:
            websocket: The WebSocket to look up.

        Returns:
            The connection wrapper or ``None`` if not tracked.
        """
        return self._connections.get(websocket)

    def get_room(self, presentation_id: str) -> _Room | None:
        """Look up a room by presentation id.

        Args:
            presentation_id: The room identifier.

        Returns:
            The room or ``None`` if it does not exist.
        """
        return self.rooms.get(presentation_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _broadcast_peer_count(self, room: _Room) -> None:
        """Broadcast a ``peer_count`` message to all connections in a room.

        Args:
            room: The room to broadcast to.
        """
        payload = PeerCountPayload(
            audience_count=room.audience_count,
            presenter_connected=room.presenter_connected,
        )
        await self.broadcast_to_room(room.presentation_id, payload.model_dump())

    async def _grace_period_cleanup(self, presentation_id: str) -> None:
        """Wait for the grace period, then destroy the room if still empty.

        Args:
            presentation_id: Room to potentially destroy.
        """
        try:
            await asyncio.sleep(_grace_period_seconds())
        except asyncio.CancelledError:
            return

        room = self.rooms.get(presentation_id)
        if room is not None and room.is_empty:
            del self.rooms[presentation_id]
            logger.info("Room '%s' destroyed after grace period", presentation_id)
