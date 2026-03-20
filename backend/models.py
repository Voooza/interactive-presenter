"""Pydantic models for the Interactive Presenter API."""

from pydantic import BaseModel


class Slide(BaseModel):
    """A single slide parsed from a Markdown presentation.

    Attributes:
        index: Zero-based position in the presentation.
        title: Text of the H1 heading that opens this slide.
        content: Raw Markdown body below the H1 (may be empty).
        poll_options: List of poll option strings if the slide contains a poll.
    """

    index: int
    title: str
    content: str
    poll_options: list[str] = []


class Presentation(BaseModel):
    """A presentation discovered on disk.

    Attributes:
        id: Filename without extension (e.g. ``demo``).
        title: Text of the first H1 found in the file.
    """

    id: str
    title: str
