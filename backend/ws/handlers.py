"""WebSocket message dispatch and route handler."""

import json
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.ws.connection_manager import ConnectionManager
from backend.ws.models import (
    ALLOWED_EMOJIS,
    ErrorPayload,
    NavigateMessage,
    PongPayload,
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

    try:
        conn = await manager.connect(websocket, presentation_id, role)
    except ValueError:
        # Presenter slot already taken.
        await websocket.close(code=4002, reason="Presenter slot taken")
        return

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
            room.current_slide = nav.slide_index

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

    else:
        error = ErrorPayload(
            code="unknown_type",
            detail=f"Unrecognized message type: {msg_type}",
        )
        await websocket.send_json(error.model_dump())
