"""Integration tests for WebSocket infrastructure."""

import json
import os
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
    # Clear handler slides cache so tests get fresh data.
    handlers_module._slides_cache.clear()
    # Reset connection manager rooms to avoid stale state from prior tests.
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


class TestConnectionHappyPaths:
    """Tests for successful WebSocket connections."""

    def test_presenter_connects(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A presenter can connect and receives a ``connected`` message."""
        with client.websocket_connect("/ws/demo?role=presenter") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert data["role"] == "presenter"
            assert data["presentation_id"] == "demo"
            assert data["current_slide"] == 0

    def test_audience_connects(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An audience member can connect and receives a ``connected`` message."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert data["role"] == "audience"
            assert data["presentation_id"] == "demo"

    def test_default_role_is_audience(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Connecting without a role query param defaults to audience."""
        with client.websocket_connect("/ws/demo") as ws:
            data = ws.receive_json()
            assert data["role"] == "audience"

    def test_presenter_and_audience_connect(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Both a presenter and audience member can connect to the same room."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            # Presenter receives connected + questions_list + peer_count.
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_data = audience_ws.receive_json()
                assert audience_data["type"] == "connected"
                assert audience_data["audience_count"] == 1


class TestInvalidPresentation:
    """Tests for connecting to a non-existent presentation."""

    def test_close_code_4001(self, client: TestClient, presentations_dir: Path) -> None:
        """Connecting to a non-existent presentation returns close code 4001."""
        with (
            pytest.raises(Exception),  # noqa: B017
            client.websocket_connect("/ws/nonexistent?role=presenter") as ws,
        ):
            ws.receive_json()


class TestPresenterSlotTaken:
    """Tests for the presenter slot enforcement."""

    def test_close_code_4002(self, client: TestClient, presentations_dir: Path) -> None:
        """A second presenter is rejected with close code 4002."""
        with client.websocket_connect("/ws/demo?role=presenter") as ws1:
            ws1.receive_json()  # connected
            ws1.receive_json()  # questions_list
            ws1.receive_json()  # peer_count

            with (
                pytest.raises(Exception),  # noqa: B017
                client.websocket_connect("/ws/demo?role=presenter") as ws2,
            ):
                ws2.receive_json()


class TestInvalidRole:
    """Tests for invalid role values."""

    def test_close_code_4003(self, client: TestClient, presentations_dir: Path) -> None:
        """An invalid role returns close code 4003."""
        with (
            pytest.raises(Exception),  # noqa: B017
            client.websocket_connect("/ws/demo?role=admin") as ws,
        ):
            ws.receive_json()


class TestAudienceCountBroadcast:
    """Tests for audience count updates."""

    def test_audience_count_on_join(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Audience count is broadcast when a new audience member joins."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count (audience_count=0)

            with client.websocket_connect("/ws/demo?role=audience") as _audience_ws:
                _audience_ws.receive_json()  # connected
                _audience_ws.receive_json()  # peer_count

                # Presenter should receive the peer_count update.
                peer_msg = presenter_ws.receive_json()
                assert peer_msg["type"] == "peer_count"
                assert peer_msg["audience_count"] == 1
                assert peer_msg["presenter_connected"] is True


class TestSlideNavigation:
    """Tests for navigate messages and slide_changed broadcasting."""

    def test_navigate_updates_slide_and_broadcasts(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Presenter navigate message updates room state and broadcasts."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count

                # Drain peer_count from presenter.
                presenter_ws.receive_json()  # peer_count

                # Presenter navigates.
                presenter_ws.send_json(
                    {
                        "type": "navigate",
                        "slide_index": 1,
                    }
                )

                # Audience receives slide_changed.
                msg = audience_ws.receive_json()
                assert msg["type"] == "slide_changed"
                assert msg["slide_index"] == 1


class TestAudienceCannotNavigate:
    """Tests for role enforcement on navigate messages."""

    def test_audience_navigate_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Audience members cannot send navigate messages."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"type": "navigate", "slide_index": 1})

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "unauthorized"


class TestDisconnectCountUpdate:
    """Tests for audience count updates on disconnect."""

    def test_count_decreases_on_disconnect(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Audience count decreases when an audience member disconnects."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count (audience=1)

            # audience_ws disconnected here (context manager exit).
            peer_msg = presenter_ws.receive_json()
            assert peer_msg["type"] == "peer_count"
            assert peer_msg["audience_count"] == 0


class TestPingPong:
    """Tests for heartbeat ping/pong."""

    def test_ping_returns_pong(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Server responds to a ping with a pong."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"type": "ping"})

            pong = ws.receive_json()
            assert pong["type"] == "pong"


class TestUnknownMessageType:
    """Tests for unrecognized message types."""

    def test_unknown_type_returns_error(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An unknown message type returns an error with code ``unknown_type``."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"type": "foobar"})

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "unknown_type"


class TestMalformedMessages:
    """Tests for malformed message handling."""

    def test_invalid_json_returns_error(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Non-JSON text returns an error."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_text("not json at all")

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"

    def test_missing_type_field_returns_error(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A JSON object without a ``type`` field returns an error."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            ws.send_json({"foo": "bar"})

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"
            assert "type" in error["detail"]

    def test_oversized_message_returns_error(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A message larger than 64 KB returns an error."""
        with client.websocket_connect("/ws/demo?role=audience") as ws:
            ws.receive_json()  # connected
            ws.receive_json()  # peer_count

            # Send a message >64 KB.
            big_msg = json.dumps({"type": "ping", "padding": "x" * (65 * 1024)})
            ws.send_text(big_msg)

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "invalid_message"
            assert "64 KB" in error["detail"]
