"""Tests for emoji reaction WebSocket messages."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.ws.models import ALLOWED_EMOJIS

_DEMO_MD = """\
# Welcome

An introductory slide.

# Second Slide

Some **bold** content here.
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
    yield tmp_path
    if old_val is None:
        del os.environ["PRESENTATIONS_DIR"]
    else:
        os.environ["PRESENTATIONS_DIR"] = old_val


@pytest.fixture()
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app)


class TestReactionHappyPath:
    """Tests for valid emoji reactions from audience members."""

    def test_reaction_forwarded_to_presenter(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An audience reaction is forwarded as reaction_broadcast to presenter."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count (audience joined)

                audience_ws.send_json({"type": "reaction", "emoji": "👍"})

                msg = presenter_ws.receive_json()
                assert msg["type"] == "reaction_broadcast"
                assert msg["emoji"] == "👍"
                assert "timestamp" in msg

    def test_all_allowed_emojis_accepted(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A sample of allowed emojis are accepted."""
        # Only test a few to stay within rate limits (5 per 3s window).
        sample_emojis = sorted(ALLOWED_EMOJIS)[:4]

        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                for emoji in sample_emojis:
                    audience_ws.send_json({"type": "reaction", "emoji": emoji})
                    msg = presenter_ws.receive_json()
                    assert msg["type"] == "reaction_broadcast"
                    assert msg["emoji"] == emoji


class TestReactionNotForwardedToAudience:
    """Tests that reactions are only sent to the presenter."""

    def test_audience_does_not_receive_reaction_broadcast(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Other audience members do not receive reaction_broadcast messages."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws1:
                audience_ws1.receive_json()  # connected
                audience_ws1.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                with client.websocket_connect("/ws/demo?role=audience") as audience_ws2:
                    audience_ws2.receive_json()  # connected
                    audience_ws2.receive_json()  # peer_count
                    presenter_ws.receive_json()  # peer_count
                    audience_ws1.receive_json()  # peer_count

                    audience_ws1.send_json({"type": "reaction", "emoji": "🎉"})

                    # Presenter gets the broadcast.
                    msg = presenter_ws.receive_json()
                    assert msg["type"] == "reaction_broadcast"

                    # Send a ping from audience_ws2 to verify no reaction was
                    # queued before it.
                    audience_ws2.send_json({"type": "ping"})
                    pong = audience_ws2.receive_json()
                    assert pong["type"] == "pong"


class TestReactionRoleEnforcement:
    """Tests that only audience members can send reactions."""

    def test_presenter_cannot_send_reaction(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Presenter sending a reaction receives an unauthorized error."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # peer_count

            presenter_ws.send_json({"type": "reaction", "emoji": "👍"})

            error = presenter_ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "unauthorized"


class TestReactionEmojiValidation:
    """Tests for emoji validation against the allowed set."""

    def test_disallowed_emoji_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An emoji not in the allowed set is rejected."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"type": "reaction", "emoji": "💀"})

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"
            assert "allowed set" in error["detail"]

    def test_empty_emoji_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An empty emoji string is rejected."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"type": "reaction", "emoji": ""})

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"

    def test_text_instead_of_emoji_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A plain text string instead of an emoji is rejected."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"type": "reaction", "emoji": "hello"})

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"


class TestReactionMissingFields:
    """Tests for missing or malformed reaction fields."""

    def test_missing_emoji_field(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A reaction without an emoji field returns an error."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"type": "reaction"})

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"


class TestReactionNoPresenter:
    """Tests for reactions when no presenter is connected."""

    def test_reaction_with_no_presenter_no_error(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Sending a reaction when no presenter is connected does not error.

        The server silently drops the broadcast since there is no presenter
        to receive it. The audience member should not receive an error.
        """
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"type": "reaction", "emoji": "🔥"})

            # Verify no error by sending a ping and getting pong back.
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"
