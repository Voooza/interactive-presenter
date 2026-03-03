"""Markdown → slide parser for the Interactive Presenter."""

from backend.models import Slide


def parse_markdown(content: str) -> list[Slide]:
    """Split a Markdown string into slides on H1 headings.

    Lines before the first ``# `` heading are ignored.  Each H1 heading
    opens a new slide whose title is the heading text.  Everything between
    that heading and the next one (or the end of the file) becomes the
    slide's content, with leading and trailing blank lines stripped.

    Args:
        content: Raw Markdown text of a presentation file.

    Returns:
        A list of :class:`~backend.models.Slide` objects in document order.
        Returns an empty list if no H1 headings are found.
    """
    slides: list[Slide] = []
    current_title: str | None = None
    current_body_lines: list[str] = []
    in_fenced_block = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fenced_block = not in_fenced_block

        if not in_fenced_block and line.startswith("# "):
            # Flush the previous slide before starting a new one.
            if current_title is not None:
                _flush(slides, current_title, current_body_lines)
            current_title = line[2:].strip()
            current_body_lines = []
        elif current_title is not None:
            current_body_lines.append(line)

    # Flush the final slide.
    if current_title is not None:
        _flush(slides, current_title, current_body_lines)

    return slides


def _flush(
    slides: list[Slide],
    title: str,
    body_lines: list[str],
) -> None:
    """Append a completed slide to *slides*.

    Leading and trailing blank lines are removed from the body before joining,
    mirroring the behaviour of Python's ``str.strip`` on the assembled block.

    Args:
        slides: Accumulator list that receives the new slide.
        title: Stripped H1 heading text.
        body_lines: Raw lines collected between this heading and the next.
    """
    # Drop leading blank lines.
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)

    # Drop trailing blank lines.
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()

    content = "\n".join(body_lines)
    slides.append(Slide(index=len(slides), title=title, content=content))
