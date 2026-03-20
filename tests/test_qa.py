"""Integration tests for the Q&A (audience questions) feature."""

import os
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.ws import handlers as handlers_module

_DEMO_MD = """\
# Welcome

An introductory slide.

# Second Slide

Some **bold** content here.

# Third Slide

More content.
"""


@pytest.fixture()
def presentations_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary presentations directory with a test Markdown file.

    Yields:
        Path to the temporary directory containing ``demo.md``.
    """
    (tmp_path / "demo.md").write_text(_DEMO_MD, encoding="utf-8")
    old_val = os.environ.get("PRESENTATIONS_DIR")
    os.environ["PRESENTATIONS_DIR"] = str(tmp_path)
    handlers_module._slides_cache.clear()
    app.state.connection_manager.rooms.clear()
    app.state.connection_manager._connections.clear()
    yield tmp_path
    handlers_module._slides_cache.clear()
    if old_val is None:
        del os.environ["PRESENTATIONS_DIR"]
    else:
        os.environ["PRESENTATIONS_DIR"] = old_val


@pytest.fixture()
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app)


def _drain_connect_messages(ws: object, role: str) -> None:
    """Consume the initial handshake messages for a connection.

    Presenter receives: connected, questions_list, peer_count.
    Audience receives: connected, peer_count.

    Args:
        ws: The WebSocket test connection.
        role: ``"presenter"`` or ``"audience"``.
    """
    ws.receive_json()  # connected  # type: ignore[union-attr]
    if role == "presenter":
        ws.receive_json()  # questions_list  # type: ignore[union-attr]
    ws.receive_json()  # peer_count  # type: ignore[union-attr]


class TestQuestionSubmitValid:
    """Tests for valid question submission."""

    def test_audience_submits_question_receives_confirmation(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Audience receives a question_received confirmation on valid submit."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json(
                {"type": "question_submit", "text": "What is the core thesis?"}
            )

            msg = ws.receive_json()
            assert msg["type"] == "question_received"
            assert msg["question"]["text"] == "What is the core thesis?"
            assert "id" in msg["question"]
            assert "slide_index" in msg["question"]
            assert "timestamp" in msg["question"]

    def test_question_tagged_with_current_slide(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Question slide_index matches the slide the presenter is on."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            _drain_connect_messages(presenter_ws, "presenter")

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                _drain_connect_messages(audience_ws, "audience")
                presenter_ws.receive_json()  # peer_count for new audience

                # Presenter navigates to slide 2.
                presenter_ws.send_json({"type": "navigate", "slide_index": 2})
                audience_ws.receive_json()  # slide_changed

                # Audience submits a question.
                audience_ws.send_json({"type": "question_submit", "text": "Hello?"})
                msg = audience_ws.receive_json()
                assert msg["type"] == "question_received"
                assert msg["question"]["slide_index"] == 2

    def test_whitespace_stripped_from_question_text(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Leading and trailing whitespace is stripped from question text."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json({"type": "question_submit", "text": "  hello  "})
            msg = ws.receive_json()
            assert msg["type"] == "question_received"
            assert msg["question"]["text"] == "hello"

    def test_question_exactly_280_chars_accepted(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A question of exactly 280 characters is accepted."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json({"type": "question_submit", "text": "a" * 280})
            msg = ws.receive_json()
            assert msg["type"] == "question_received"
            assert len(msg["question"]["text"]) == 280


class TestQuestionSubmitRejected:
    """Tests for invalid question content."""

    def test_empty_text_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An empty question text is rejected with invalid_message."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json({"type": "question_submit", "text": ""})
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"

    def test_whitespace_only_text_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A whitespace-only question is rejected with invalid_message."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json({"type": "question_submit", "text": "   "})
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"
            assert "empty" in error["detail"].lower()

    def test_text_281_chars_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A question of 281 characters is rejected with invalid_message."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json({"type": "question_submit", "text": "a" * 281})
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"
            assert "280" in error["detail"]

    def test_missing_text_field_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A question_submit with no text field is rejected."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json({"type": "question_submit"})
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"


class TestRoleEnforcement:
    """Tests for role enforcement on Q&A messages."""

    def test_presenter_cannot_submit_question(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Presenter sending question_submit receives an unauthorized error."""
        with client.websocket_connect("/ws/demo?role=presenter") as ws:
            _drain_connect_messages(ws, "presenter")

            ws.send_json({"type": "question_submit", "text": "Can I ask this?"})
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "unauthorized"

    def test_audience_cannot_get_questions(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Audience sending get_questions receives an unauthorized error."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json({"type": "get_questions"})
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "unauthorized"


class TestPresenterNotification:
    """Tests for presenter receiving question notifications."""

    def test_presenter_notified_when_audience_submits(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Presenter receives question_notify when audience submits."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            _drain_connect_messages(presenter_ws, "presenter")

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                _drain_connect_messages(audience_ws, "audience")
                presenter_ws.receive_json()  # peer_count for audience join

                audience_ws.send_json(
                    {"type": "question_submit", "text": "Great talk!"}
                )

                # Audience gets confirmation.
                audience_ws.receive_json()

                # Presenter gets notification.
                note = presenter_ws.receive_json()
                assert note["type"] == "question_notify"
                assert note["question"]["text"] == "Great talk!"

    def test_no_crash_when_presenter_absent(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Submitter still gets confirmation when no presenter is connected."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            ws.send_json({"type": "question_submit", "text": "Anyone home?"})
            msg = ws.receive_json()
            assert msg["type"] == "question_received"
            assert msg["question"]["text"] == "Anyone home?"


class TestGetQuestions:
    """Tests for the get_questions handler."""

    def test_get_questions_returns_empty_list(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """get_questions on a fresh room returns an empty questions list."""
        with client.websocket_connect("/ws/demo?role=presenter") as ws:
            _drain_connect_messages(ws, "presenter")

            ws.send_json({"type": "get_questions"})
            msg = ws.receive_json()
            assert msg["type"] == "questions_list"
            assert msg["questions"] == []

    def test_get_questions_returns_all_questions(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """get_questions returns all submitted questions in order."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            _drain_connect_messages(presenter_ws, "presenter")

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                _drain_connect_messages(audience_ws, "audience")
                presenter_ws.receive_json()  # peer_count

                # Submit two questions.
                audience_ws.send_json(
                    {"type": "question_submit", "text": "First question"}
                )
                audience_ws.receive_json()  # confirmation
                presenter_ws.receive_json()  # notification

                audience_ws.send_json(
                    {"type": "question_submit", "text": "Second question"}
                )
                audience_ws.receive_json()  # confirmation
                presenter_ws.receive_json()  # notification

                # Presenter requests the list.
                presenter_ws.send_json({"type": "get_questions"})
                msg = presenter_ws.receive_json()

            assert msg["type"] == "questions_list"
            assert len(msg["questions"]) == 2
            assert msg["questions"][0]["text"] == "First question"
            assert msg["questions"][1]["text"] == "Second question"


class TestPresenterConnectAutoList:
    """Tests for automatic questions_list on presenter connect."""

    def test_presenter_receives_questions_list_on_connect(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Presenter receives questions_list during connect handshake."""
        # First, have an audience member submit questions without a presenter.
        with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
            _drain_connect_messages(audience_ws, "audience")

            audience_ws.send_json(
                {"type": "question_submit", "text": "Before presenter"}
            )
            audience_ws.receive_json()  # confirmation (no presenter to notify)

            # Now the presenter connects.
            with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
                connected = presenter_ws.receive_json()
                assert connected["type"] == "connected"

                # Second message is questions_list.
                qlist = presenter_ws.receive_json()
                assert qlist["type"] == "questions_list"
                assert len(qlist["questions"]) == 1
                assert qlist["questions"][0]["text"] == "Before presenter"

    def test_presenter_receives_empty_questions_list_on_first_connect(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Presenter receives an empty questions_list when no questions exist yet."""
        with client.websocket_connect("/ws/demo?role=presenter") as ws:
            connected = ws.receive_json()
            assert connected["type"] == "connected"

            qlist = ws.receive_json()
            assert qlist["type"] == "questions_list"
            assert qlist["questions"] == []


class TestRateLimiting:
    """Tests for question_submit rate limiting (3 per 60 seconds)."""

    def test_fourth_submit_within_window_is_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """The 4th question_submit within 60 s is rate-limited."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            for i in range(3):
                ws.send_json({"type": "question_submit", "text": f"Question {i + 1}"})
                msg = ws.receive_json()
                assert msg["type"] == "question_received", (
                    f"Expected success on submit {i + 1}"
                )

            # 4th submit should be rate-limited.
            ws.send_json({"type": "question_submit", "text": "One too many"})
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "rate_limited"

    def test_submit_allowed_after_window_expires(
        self,
        client: TestClient,
        presentations_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After the 60-second window expires, submits are allowed again."""
        import backend.ws.rate_limiter as rl_module

        original_monotonic = time.monotonic

        # Use a controlled clock: start at t=0.
        clock: list[float] = [0.0]

        def fake_monotonic() -> float:
            return clock[0]

        monkeypatch.setattr(rl_module.time, "monotonic", fake_monotonic)

        with client.websocket_connect("/ws/demo?role=audience") as ws:
            _drain_connect_messages(ws, "audience")

            # Submit 3 questions at t=0.
            for i in range(3):
                ws.send_json({"type": "question_submit", "text": f"Q{i}"})
                ws.receive_json()

            # 4th at t=0 should be rejected.
            ws.send_json({"type": "question_submit", "text": "rejected"})
            error = ws.receive_json()
            assert error["code"] == "rate_limited"

            # Advance clock past 60-second window.
            clock[0] = 61.0

            # Now the 5th submit should succeed.
            ws.send_json({"type": "question_submit", "text": "after window"})
            msg = ws.receive_json()
            assert msg["type"] == "question_received"

        # Restore real monotonic just to be safe.
        monkeypatch.setattr(rl_module.time, "monotonic", original_monotonic)
