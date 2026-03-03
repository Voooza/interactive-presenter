"""Unit tests for backend.parser.parse_markdown."""

import pytest

from backend.models import Slide
from backend.parser import parse_markdown


class TestParseMarkdownBasics:
    """Basic parsing behaviour."""

    def test_single_slide_no_body(self) -> None:
        """A lone H1 with no body produces one slide with empty content."""
        slides = parse_markdown("# Hello")
        assert len(slides) == 1
        assert slides[0] == Slide(index=0, title="Hello", content="")

    def test_single_slide_with_body(self) -> None:
        """Body lines below an H1 are captured as content."""
        md = "# Title\n\nSome body text.\n"
        slides = parse_markdown(md)
        assert len(slides) == 1
        assert slides[0].title == "Title"
        assert slides[0].content == "Some body text."

    def test_multiple_slides(self) -> None:
        """Each H1 starts a new slide; indices are sequential."""
        md = "# First\n\nBody one.\n\n# Second\n\nBody two.\n"
        slides = parse_markdown(md)
        assert len(slides) == 2
        assert slides[0].index == 0
        assert slides[0].title == "First"
        assert slides[0].content == "Body one."
        assert slides[1].index == 1
        assert slides[1].title == "Second"
        assert slides[1].content == "Body two."

    def test_five_slides(self) -> None:
        """Verify correct indexing across five slides."""
        md = "\n".join(f"# Slide {i}\n\nContent {i}." for i in range(5))
        slides = parse_markdown(md)
        assert len(slides) == 5
        for i, slide in enumerate(slides):
            assert slide.index == i
            assert slide.title == f"Slide {i}"
            assert slide.content == f"Content {i}."


class TestParseMarkdownEdgeCases:
    """Edge-case and boundary behaviour."""

    def test_empty_string(self) -> None:
        """Empty input yields no slides."""
        assert parse_markdown("") == []

    def test_no_h1_headings(self) -> None:
        """Content with no H1 headings yields no slides."""
        md = "## Not an H1\n\nSome text.\n\n### Also not H1\n"
        assert parse_markdown(md) == []

    def test_lines_before_first_h1_are_ignored(self) -> None:
        """Preamble lines before the first H1 are discarded."""
        md = "This is a preamble.\nAnother line.\n\n# Real Slide\n\nBody here.\n"
        slides = parse_markdown(md)
        assert len(slides) == 1
        assert slides[0].title == "Real Slide"
        assert slides[0].content == "Body here."

    def test_trailing_whitespace_stripped_from_title(self) -> None:
        """Trailing spaces on the H1 line are stripped from the title."""
        slides = parse_markdown("# My Title   \n\nContent.\n")
        assert slides[0].title == "My Title"

    def test_trailing_blank_lines_stripped_from_content(self) -> None:
        """Trailing blank lines in a slide body are stripped."""
        md = "# Slide\n\nContent line.\n\n\n"
        slides = parse_markdown(md)
        assert slides[0].content == "Content line."

    def test_content_with_only_blank_lines(self) -> None:
        """A body that is entirely blank lines yields empty content."""
        md = "# Slide\n\n\n\n"
        slides = parse_markdown(md)
        assert slides[0].content == ""

    def test_h2_inside_slide_is_part_of_content(self) -> None:
        """H2 headings inside a slide are captured as content, not new slides."""
        md = "# Slide\n\n## Sub-heading\n\nParagraph.\n"
        slides = parse_markdown(md)
        assert len(slides) == 1
        assert "## Sub-heading" in slides[0].content

    def test_fenced_code_block_in_content(self) -> None:
        """Fenced code blocks are preserved verbatim in content."""
        md = "# Code Slide\n\n```python\nprint('hello')\n```\n"
        slides = parse_markdown(md)
        assert "```python" in slides[0].content
        assert "print('hello')" in slides[0].content

    def test_h1_inside_fenced_code_block_not_a_slide_break(self) -> None:
        """H1 headings inside fenced code blocks must not split slides."""
        md = (
            "# Code Example\n\n"
            "Here is a sample:\n\n"
            "```markdown\n"
            "# My First Slide\n\n"
            "Hello, world!\n\n"
            "# My Second Slide\n\n"
            "More content here.\n"
            "```\n"
        )
        slides = parse_markdown(md)
        assert len(slides) == 1
        assert slides[0].title == "Code Example"
        assert "# My First Slide" in slides[0].content
        assert "# My Second Slide" in slides[0].content

    def test_h1_inside_tilde_fenced_code_block_not_a_slide_break(self) -> None:
        """H1 headings inside ~~~-fenced code blocks must not split slides."""
        md = (
            "# Code Example\n\n"
            "~~~\n"
            "# Not a slide\n"
            "~~~\n"
        )
        slides = parse_markdown(md)
        assert len(slides) == 1
        assert "# Not a slide" in slides[0].content

    def test_h1_after_fenced_code_block_is_a_slide_break(self) -> None:
        """H1 headings after a closed fenced block should still split slides."""
        md = (
            "# First\n\n"
            "```\n"
            "# Not a slide\n"
            "```\n\n"
            "# Second\n\n"
            "Body two.\n"
        )
        slides = parse_markdown(md)
        assert len(slides) == 2
        assert slides[0].title == "First"
        assert "# Not a slide" in slides[0].content
        assert slides[1].title == "Second"
        assert slides[1].content == "Body two."

    def test_bold_and_italic_preserved(self) -> None:
        """Inline Markdown formatting survives the parser untouched."""
        md = "# Rich\n\nThis is **bold** and *italic*.\n"
        slides = parse_markdown(md)
        assert "**bold**" in slides[0].content
        assert "*italic*" in slides[0].content

    def test_returns_list_of_slide_instances(self) -> None:
        """parse_markdown always returns Slide objects."""
        slides = parse_markdown("# A\n\n# B\n")
        assert all(isinstance(s, Slide) for s in slides)

    @pytest.mark.parametrize(
        "heading_line",
        [
            "#No space",
            "## H2",
            "### H3",
            "#",
        ],
    )
    def test_non_h1_headings_not_treated_as_slide_break(
        self, heading_line: str
    ) -> None:
        """Lines that look like headings but are not ``# `` are not slide breaks."""
        md = f"# Slide One\n\n{heading_line}\n\nMore text.\n"
        slides = parse_markdown(md)
        assert len(slides) == 1
