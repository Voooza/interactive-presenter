"""API routes for the Interactive Presenter."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.models import Presentation, Slide
from backend.parser import parse_markdown

router = APIRouter()

_DEFAULT_PRESENTATIONS_DIR = "presentations"


def _presentations_dir() -> Path:
    """Return the configured presentations directory as a :class:`~pathlib.Path`.

    The directory is read from the ``PRESENTATIONS_DIR`` environment variable.
    Falls back to ``presentations/`` relative to the current working directory.

    Returns:
        Absolute :class:`~pathlib.Path` to the presentations directory.
    """
    raw = os.environ.get("PRESENTATIONS_DIR", _DEFAULT_PRESENTATIONS_DIR)
    return Path(raw)


@router.get("/api/presentations", response_model=list[Presentation])
def list_presentations() -> list[Presentation]:
    """List all presentations available in the presentations directory.

    Scans ``PRESENTATIONS_DIR`` for ``.md`` files and returns a
    :class:`~backend.models.Presentation` for each one, using the first H1
    heading as the title (or the bare filename if none is found).

    Returns:
        A list of :class:`~backend.models.Presentation` objects, one per file.
    """
    presentations_dir = _presentations_dir()
    if not presentations_dir.is_dir():
        return []

    presentations: list[Presentation] = []
    for md_file in sorted(presentations_dir.glob("*.md")):
        presentation_id = md_file.stem
        title = _extract_title(md_file)
        presentations.append(Presentation(id=presentation_id, title=title))

    return presentations


@router.get("/api/presentations/{presentation_id}/slides", response_model=list[Slide])
def get_slides(presentation_id: str) -> list[Slide]:
    """Return the parsed slides for a given presentation.

    Args:
        presentation_id: The presentation identifier (filename without
            ``.md`` extension).

    Returns:
        An ordered list of :class:`~backend.models.Slide` objects.

    Raises:
        HTTPException: 404 if no matching ``.md`` file exists.
    """
    md_file = _presentations_dir() / f"{presentation_id}.md"
    if not md_file.is_file():
        raise HTTPException(status_code=404, detail="Presentation not found")

    content = md_file.read_text(encoding="utf-8")
    return parse_markdown(content)


def _extract_title(md_file: Path) -> str:
    """Read the first H1 heading from a Markdown file.

    Args:
        md_file: Path to the ``.md`` file.

    Returns:
        The H1 heading text, or the bare filename stem if no H1 is found.
    """
    for line in md_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return md_file.stem
