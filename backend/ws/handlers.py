"""WebSocket message dispatch and route handler."""

import json
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.models import Slide
from backend.parser import parse_markdown
from backend.ws.connection_manager import ConnectionManager, _PollState
from backend.ws.models import (
    ALLOWED_EMOJIS,
    ErrorPayload,
    GetQuestionsMessage,
    NavigateMessage,
    PollClosedPayload,
    PollOpenedPayload,
    PollResultsPayload,
    PollVoteMessage,
    PongPayload,
    QuestionData,
    QuestionNotifyPayload,
    QuestionReceivedPayload,
    QuestionsListPayload,
    QuestionSubmitMessage,
    ReactionBroadcastPayload,
    ReactionMessage,
    SlideChangedPayload,
)
from backend.ws.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

ws_router = APIRouter()

_DEFAULT_PRESENTATIONS_DIR = "presentations"
_MAX_MESSAGE_SIZE = 64 * 1024  # 64 KB
_IDLE_TIMEOUT_DEFAULT = 60

# Cache parsed slides per presentation_id so we don't re-parse on every navigate.
_slides_cache: dict[str, list[Slide]] = {}


def _presentations_dir() -> Path:
    """Return the configured presentations directory."""
    raw = os.environ.get("PRESENTATIONS_DIR", _DEFAULT_PRESENTATIONS_DIR)
    return Path(raw)


def _idle_timeout_seconds() -> float:
    """Return the configured idle timeout in seconds."""
    return float(os.environ.get("WS_IDLE_TIMEOUT_SECONDS", str(_IDLE_TIMEOUT_DEFAULT)))


def _presentation_exists(presentation_id: str) -> bool:
    """Check whether a presentation file exists on disk.

    Args:
        presentation_id: The presentation identifier (filename stem).

    Returns:
        ``True`` if the corresponding ``.md`` file exists.
    """
    md_file = _presentations_dir() / f"{presentation_id}.md"
    return md_file.is_file()


def _get_slides(presentation_id: str) -> list[Slide]:
    """Return parsed slides for a presentation, using an in-memory cache.

    Args:
        presentation_id: The presentation identifier (filename stem).

    Returns:
        A list of Slide objects.
    """
    if presentation_id not in _slides_cache:
        md_file = _presentations_dir() / f"{presentation_id}.md"
        content = md_file.read_text(encoding="utf-8")
        _slides_cache[presentation_id] = parse_markdown(content)
    return _slides_cache[presentation_id]


@ws_router.websocket("/ws/{presentation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    presentation_id: str,
    role: str = "audience",
) -> None:
    """Handle a WebSocket connection for a presentation room.

    Args:
        websocket: The incoming WebSocket connection.
        presentation_id: Which presentation to join.
        role: ``"presenter"`` or ``"audience"`` (default).
    """
    manager: ConnectionManager = websocket.app.state.connection_manager

    # Validate role.
    if role not in ("presenter", "audience"):
        await websocket.accept()
        await websocket.close(code=4003, reason="Invalid role")
        return

    # Validate presentation exists.
    if not _presentation_exists(presentation_id):
        await websocket.accept()
        await websocket.close(code=4001, reason="Presentation not found")
        return

    # Accept and connect.
    await websocket.accept()
    conn = await manager.connect(websocket, presentation_id, role)

    rate_limiter = RateLimiter()

    try:
        while True:
            raw = await websocket.receive_text()

            # Enforce message size limit.
            if len(raw) > _MAX_MESSAGE_SIZE:
                error = ErrorPayload(
                    code="invalid_message",
                    detail="Message exceeds 64 KB size limit",
                )
                await websocket.send_json(error.model_dump())
                continue

            # Update last-message timestamp for idle detection.
            conn.last_message_at = time.monotonic()

            # Parse JSON.
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                error = ErrorPayload(
                    code="invalid_message",
                    detail="Invalid JSON",
                )
                await websocket.send_json(error.model_dump())
                continue

            if not isinstance(data, dict) or "type" not in data:
                error = ErrorPayload(
                    code="invalid_message",
                    detail="Missing required field: type",
                )
                await websocket.send_json(error.model_dump())
                continue

            msg_type = data.get("type")

            # Rate limiting.
            if not rate_limiter.check(str(msg_type)):
                error = ErrorPayload(
                    code="rate_limited",
                    detail="Too many messages, slow down",
                )
                await websocket.send_json(error.model_dump())
                continue

            # Dispatch by type.
            await _dispatch(manager, websocket, conn.role, presentation_id, data)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception(
            "Unexpected error in WebSocket handler for %s", presentation_id
        )
    finally:
        await manager.disconnect(websocket)


async def _dispatch(
    manager: ConnectionManager,
    websocket: WebSocket,
    role: str,
    presentation_id: str,
    data: dict[str, object],
) -> None:
    """Route an incoming message to the appropriate handler.

    Args:
        manager: The connection manager.
        websocket: The sender's WebSocket.
        role: The sender's role.
        presentation_id: The room identifier.
        data: Parsed JSON message dict.
    """
    msg_type = data.get("type")

    if msg_type == "ping":
        pong = PongPayload()
        await websocket.send_json(pong.model_dump())

    elif msg_type == "navigate":
        if role != "presenter":
            error = ErrorPayload(
                code="unauthorized",
                detail="Only the presenter can navigate",
            )
            await websocket.send_json(error.model_dump())
            return

        try:
            nav = NavigateMessage(**data)  # type: ignore[arg-type]
        except ValidationError as exc:
            error = ErrorPayload(
                code="invalid_message",
                detail=str(exc),
            )
            await websocket.send_json(error.model_dump())
            return

        room = manager.get_room(presentation_id)
        if room is not None:
            old_slide = room.current_slide
            room.current_slide = nav.slide_index

            # Handle poll lifecycle on slide transitions.
            await _handle_poll_lifecycle(
                manager, presentation_id, old_slide, nav.slide_index
            )

        slide_changed = SlideChangedPayload(slide_index=nav.slide_index)
        await manager.send_to_audience(presentation_id, slide_changed.model_dump())

    elif msg_type == "reaction":
        if role != "audience":
            error = ErrorPayload(
                code="unauthorized",
                detail="Only audience members can send reactions",
            )
            await websocket.send_json(error.model_dump())
            return

        try:
            reaction = ReactionMessage(**data)  # type: ignore[arg-type]
        except ValidationError as exc:
            error = ErrorPayload(
                code="invalid_message",
                detail=str(exc),
            )
            await websocket.send_json(error.model_dump())
            return

        if reaction.emoji not in ALLOWED_EMOJIS:
            error = ErrorPayload(
                code="invalid_message",
                detail=f"Emoji not in allowed set: {reaction.emoji}",
            )
            await websocket.send_json(error.model_dump())
            return

        broadcast = ReactionBroadcastPayload(emoji=reaction.emoji)
        await manager.send_to_presenter(presentation_id, broadcast.model_dump())

    elif msg_type == "poll_vote":
        if role != "audience":
            error = ErrorPayload(
                code="unauthorized",
                detail="Only audience members can vote",
            )
            await websocket.send_json(error.model_dump())
            return

        try:
            vote = PollVoteMessage(**data)  # type: ignore[arg-type]
        except ValidationError as exc:
            error = ErrorPayload(
                code="invalid_message",
                detail=str(exc),
            )
            await websocket.send_json(error.model_dump())
            return

        await _handle_poll_vote(manager, websocket, presentation_id, vote)

    elif msg_type == "question_submit":
        if role != "audience":
            error = ErrorPayload(
                code="unauthorized",
                detail="Only audience members can submit questions",
            )
            await websocket.send_json(error.model_dump())
            return

        try:
            question_msg = QuestionSubmitMessage(**data)  # type: ignore[arg-type]
        except ValidationError as exc:
            error = ErrorPayload(
                code="invalid_message",
                detail=str(exc),
            )
            await websocket.send_json(error.model_dump())
            return

        await _handle_question_submit(manager, websocket, presentation_id, question_msg)

    elif msg_type == "get_questions":
        if role != "presenter":
            error = ErrorPayload(
                code="unauthorized",
                detail="Only the presenter can request questions",
            )
            await websocket.send_json(error.model_dump())
            return

        try:
            GetQuestionsMessage(**data)  # type: ignore[arg-type]
        except ValidationError as exc:
            error = ErrorPayload(
                code="invalid_message",
                detail=str(exc),
            )
            await websocket.send_json(error.model_dump())
            return

        await _handle_get_questions(manager, websocket, presentation_id)

    else:
        error = ErrorPayload(
            code="unknown_type",
            detail=f"Unrecognized message type: {msg_type}",
        )
        await websocket.send_json(error.model_dump())


async def _handle_poll_lifecycle(
    manager: ConnectionManager,
    presentation_id: str,
    old_slide: int,
    new_slide: int,
) -> None:
    """Send poll_closed / poll_opened messages on slide transitions.

    Args:
        manager: The connection manager.
        presentation_id: The room identifier.
        old_slide: The slide index being navigated away from.
        new_slide: The slide index being navigated to.
    """
    room = manager.get_room(presentation_id)
    if room is None:
        return

    slides = _get_slides(presentation_id)

    # Close poll on the old slide if it was a poll slide.
    if 0 <= old_slide < len(slides) and slides[old_slide].poll_options:
        poll_state = room.polls.get(old_slide)
        if poll_state is not None:
            closed = PollClosedPayload(
                slide_index=old_slide,
                options=poll_state.options,
                results=list(poll_state.votes),
            )
            await manager.broadcast_to_room(presentation_id, closed.model_dump())
        room.active_poll = None

    # Open poll on the new slide if it is a poll slide.
    if 0 <= new_slide < len(slides) and slides[new_slide].poll_options:
        poll_state = room.polls.get(new_slide)
        if poll_state is None:
            poll_state = _PollState(
                slide_index=new_slide,
                options=slides[new_slide].poll_options,
            )
            room.polls[new_slide] = poll_state

        room.active_poll = new_slide
        opened = PollOpenedPayload(
            slide_index=new_slide,
            options=poll_state.options,
            results=list(poll_state.votes),
        )
        await manager.broadcast_to_room(presentation_id, opened.model_dump())


async def _handle_poll_vote(
    manager: ConnectionManager,
    websocket: WebSocket,
    presentation_id: str,
    vote: PollVoteMessage,
) -> None:
    """Process a poll vote from an audience member.

    Args:
        manager: The connection manager.
        websocket: The voter's WebSocket.
        presentation_id: The room identifier.
        vote: The validated vote message.
    """
    room = manager.get_room(presentation_id)
    if room is None:
        return

    # Check that there is an active poll for the voted slide.
    if room.active_poll != vote.slide_index:
        error = ErrorPayload(
            code="invalid_vote",
            detail="No active poll for this slide",
        )
        await websocket.send_json(error.model_dump())
        return

    poll_state = room.polls.get(vote.slide_index)
    if poll_state is None:
        error = ErrorPayload(
            code="invalid_vote",
            detail="Poll not found",
        )
        await websocket.send_json(error.model_dump())
        return

    # Validate option index.
    if vote.option_index < 0 or vote.option_index >= len(poll_state.options):
        error = ErrorPayload(
            code="invalid_vote",
            detail="Invalid option index",
        )
        await websocket.send_json(error.model_dump())
        return

    # Check for duplicate vote (use id of websocket object).
    voter_id = id(websocket)
    if voter_id in poll_state.voters:
        error = ErrorPayload(
            code="already_voted",
            detail="You have already voted on this poll",
        )
        await websocket.send_json(error.model_dump())
        return

    # Record vote.
    poll_state.voters.add(voter_id)
    poll_state.votes[vote.option_index] += 1

    # Broadcast updated results to everyone.
    results = PollResultsPayload(
        slide_index=vote.slide_index,
        options=poll_state.options,
        results=list(poll_state.votes),
    )
    await manager.broadcast_to_room(presentation_id, results.model_dump())


_MAX_QUESTION_LENGTH = 280


async def _handle_question_submit(
    manager: ConnectionManager,
    websocket: WebSocket,
    presentation_id: str,
    question_msg: QuestionSubmitMessage,
) -> None:
    """Process a question submission from an audience member.

    Validates the text length (1–280 chars), stores the question in the room,
    confirms receipt to the sender, and notifies the presenter.

    Args:
        manager: The connection manager.
        websocket: The submitter's WebSocket.
        presentation_id: The room identifier.
        question_msg: The validated question submission message.
    """
    text = question_msg.text.strip()

    if not text:
        error = ErrorPayload(
            code="invalid_message",
            detail="Question text must not be empty",
        )
        await websocket.send_json(error.model_dump())
        return

    if len(text) > _MAX_QUESTION_LENGTH:
        error = ErrorPayload(
            code="invalid_message",
            detail=f"Question text must be at most {_MAX_QUESTION_LENGTH} characters",
        )
        await websocket.send_json(error.model_dump())
        return

    room = manager.get_room(presentation_id)
    if room is None:
        return

    # Assign an auto-incrementing ID.
    question_id = room._next_question_id
    room._next_question_id += 1

    question = QuestionData(
        id=question_id,
        text=text,
        slide_index=room.current_slide,
        timestamp=question_msg.timestamp,
    )
    room.questions.append(question)

    # Confirm receipt to the sender.
    received = QuestionReceivedPayload(question=question)
    await websocket.send_json(received.model_dump())

    # Notify the presenter.
    notify = QuestionNotifyPayload(question=question)
    await manager.send_to_presenter(presentation_id, notify.model_dump())


async def _handle_get_questions(
    manager: ConnectionManager,
    websocket: WebSocket,
    presentation_id: str,
) -> None:
    """Send the full question list to the requesting presenter.

    Args:
        manager: The connection manager.
        websocket: The presenter's WebSocket.
        presentation_id: The room identifier.
    """
    room = manager.get_room(presentation_id)
    if room is None:
        return

    payload = QuestionsListPayload(questions=list(room.questions))
    await websocket.send_json(payload.model_dump())
