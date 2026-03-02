"""Integration tests for the Interactive Presenter API routes."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

_DEMO_MD = """\
# Welcome

An introductory slide.

# Second Slide

Some **bold** content here.

# Third Slide

```python
print("hello")
```
"""


@pytest.fixture()
def presentations_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary presentations directory with a test Markdown file.

    Yields:
        Path to the temporary directory containing ``test_deck.md``.
    """
    (tmp_path / "test_deck.md").write_text(_DEMO_MD, encoding="utf-8")
    old_val = os.environ.get("PRESENTATIONS_DIR")
    os.environ["PRESENTATIONS_DIR"] = str(tmp_path)
    yield tmp_path
    # Restore original env var.
    if old_val is None:
        del os.environ["PRESENTATIONS_DIR"]
    else:
        os.environ["PRESENTATIONS_DIR"] = old_val


@pytest.fixture()
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app)


class TestListPresentations:
    """Tests for GET /api/presentations."""

    def test_returns_200_with_presentations(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """The endpoint returns 200 and a non-empty list."""
        response = client.get("/api/presentations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_presentation_shape(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Each presentation object has ``id`` and ``title`` fields."""
        response = client.get("/api/presentations")
        item = response.json()[0]
        assert "id" in item
        assert "title" in item

    def test_presentation_id_is_filename_stem(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """The ``id`` field matches the filename without the ``.md`` extension."""
        response = client.get("/api/presentations")
        assert response.json()[0]["id"] == "test_deck"

    def test_presentation_title_is_first_h1(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """The ``title`` field is taken from the first H1 in the file."""
        response = client.get("/api/presentations")
        assert response.json()[0]["title"] == "Welcome"

    def test_empty_dir_returns_empty_list(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """An empty (but existing) directory returns an empty list."""
        os.environ["PRESENTATIONS_DIR"] = str(tmp_path)
        response = client.get("/api/presentations")
        assert response.status_code == 200
        assert response.json() == []

    def test_missing_dir_returns_empty_list(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """A non-existent directory returns an empty list without crashing."""
        os.environ["PRESENTATIONS_DIR"] = str(tmp_path / "does_not_exist")
        response = client.get("/api/presentations")
        assert response.status_code == 200
        assert response.json() == []

    def test_multiple_files_all_returned(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Multiple ``.md`` files in the directory are all listed."""
        (presentations_dir / "second.md").write_text(
            "# Second\n\nContent.", encoding="utf-8"
        )
        response = client.get("/api/presentations")
        ids = {p["id"] for p in response.json()}
        assert ids == {"test_deck", "second"}


class TestGetSlides:
    """Tests for GET /api/presentations/{id}/slides."""

    def test_returns_200_with_slides(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Requesting slides for an existing presentation returns 200."""
        response = client.get("/api/presentations/test_deck/slides")
        assert response.status_code == 200

    def test_slide_count(self, client: TestClient, presentations_dir: Path) -> None:
        """The correct number of slides is returned."""
        response = client.get("/api/presentations/test_deck/slides")
        assert len(response.json()) == 3

    def test_slide_shape(self, client: TestClient, presentations_dir: Path) -> None:
        """Each slide object has ``index``, ``title``, and ``content`` fields."""
        response = client.get("/api/presentations/test_deck/slides")
        slide = response.json()[0]
        assert "index" in slide
        assert "title" in slide
        assert "content" in slide

    def test_first_slide_index_is_zero(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """The first slide's index is 0."""
        response = client.get("/api/presentations/test_deck/slides")
        assert response.json()[0]["index"] == 0

    def test_slide_titles(self, client: TestClient, presentations_dir: Path) -> None:
        """Slide titles match the H1 headings in document order."""
        response = client.get("/api/presentations/test_deck/slides")
        titles = [s["title"] for s in response.json()]
        assert titles == ["Welcome", "Second Slide", "Third Slide"]

    def test_slide_content(self, client: TestClient, presentations_dir: Path) -> None:
        """Slide content is populated from the body below the H1."""
        response = client.get("/api/presentations/test_deck/slides")
        assert response.json()[0]["content"] == "An introductory slide."

    def test_404_for_missing_presentation(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Requesting an unknown presentation id returns 404."""
        response = client.get("/api/presentations/nonexistent/slides")
        assert response.status_code == 404

    def test_404_detail_message(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """The 404 response body contains the expected detail message."""
        response = client.get("/api/presentations/nonexistent/slides")
        assert response.json() == {"detail": "Presentation not found"}

    def test_code_block_in_slide_content(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Fenced code blocks inside a slide are preserved in the content."""
        response = client.get("/api/presentations/test_deck/slides")
        third_slide = response.json()[2]
        assert "```python" in third_slide["content"]
        assert 'print("hello")' in third_slide["content"]
