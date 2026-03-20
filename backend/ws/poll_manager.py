"""Poll state management for a single room."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.models import PollDefinition


@dataclass
class PollState:
    """Runtime poll state held in memory for a single room.

    Attributes:
        poll_id: Stable identifier in the form ``"<presentation_id>:<slide_index>"``.
        slide_index: Zero-based index of the slide that owns this poll.
        options: Ordered list of option labels (2–6 items).
        votes: Vote count per option, parallel to ``options``.
        voted_ids: Set of connection object ids that have already voted.
            Never sent to clients.
        is_open: ``True`` while the poll is accepting votes.
    """

    poll_id: str
    slide_index: int
    options: list[str]
    votes: list[int]
    voted_ids: set[int] = field(default_factory=set)
    is_open: bool = True


def open_poll(room: object, poll_def: PollDefinition) -> PollState:
    """Create a fresh :class:`PollState` on *room* and return it.

    The new state has all vote counts set to zero and ``is_open = True``.
    Any previously attached poll state on the room is replaced.

    Args:
        room: The ``_Room`` instance that owns this poll.  Typed as
            ``object`` to avoid a circular import; the ``active_poll``
            attribute is set via ``setattr``.
        poll_def: The poll definition extracted from the parsed slide.

    Returns:
        The newly created :class:`PollState`.
    """
    presentation_id: str = room.presentation_id
    poll_id = f"{presentation_id}:{poll_def.slide_index}"
    state = PollState(
        poll_id=poll_id,
        slide_index=poll_def.slide_index,
        options=list(poll_def.options),
        votes=[0] * len(poll_def.options),
    )
    room.active_poll = state  # type: ignore[attr-defined]
    return state


def close_poll(room: object) -> PollState | None:
    """Mark the active poll as closed, detach it from *room*, and return it.

    Args:
        room: The ``_Room`` instance.

    Returns:
        The final :class:`PollState` (with ``is_open = False``), or ``None``
        if there was no active poll.
    """
    state: PollState | None = getattr(room, "active_poll", None)
    if state is None:
        return None
    state.is_open = False
    room.active_poll = None  # type: ignore[attr-defined]
    return state


def record_vote(
    poll: PollState,
    option_index: int,
    connection_id: int,
) -> None:
    """Increment the vote count for *option_index* and record *connection_id*.

    Args:
        poll: The currently open :class:`PollState`.
        option_index: Zero-based index of the chosen option.
        connection_id: ``id()`` of the ``_Connection`` object.  Never
            shared with clients.

    Raises:
        ValueError: If *connection_id* has already voted in this poll.
        IndexError: If *option_index* is out of range.
    """
    if connection_id in poll.voted_ids:
        raise ValueError("You have already voted in this poll")
    if option_index < 0 or option_index >= len(poll.votes):
        raise IndexError("Invalid option index")
    poll.votes[option_index] += 1
    poll.voted_ids.add(connection_id)
