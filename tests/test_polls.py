"""Tests for the polls feature (parser, WS handlers, vote lifecycle)."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.parser import parse_markdown
from backend.ws import handlers as handlers_module

_POLL_MD = """\
# Welcome

An introductory slide.

# Quick Poll

What is your favourite colour?

<!-- poll
- Red
- Green
- Blue
-->

# Results

The results are in!
"""


@pytest.fixture()
def presentations_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary presentations directory with a poll-enabled demo.

    Yields:
        Path to the temporary directory containing ``demo.md``.
    """
    (tmp_path / "demo.md").write_text(_POLL_MD, encoding="utf-8")
    old_val = os.environ.get("PRESENTATIONS_DIR")
    os.environ["PRESENTATIONS_DIR"] = str(tmp_path)
    # Clear handler slides cache so tests get fresh data.
    handlers_module._slides_cache.clear()
    # Reset connection manager rooms to avoid stale poll state from prior tests.
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


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestPollParsing:
    """Tests for poll option extraction from Markdown."""

    def test_slide_with_poll_has_options(self) -> None:
        """A slide with a ``<!-- poll -->`` block gets poll_options populated."""
        slides = parse_markdown(_POLL_MD)
        poll_slide = slides[1]
        assert poll_slide.title == "Quick Poll"
        assert poll_slide.poll_options == ["Red", "Green", "Blue"]

    def test_slide_without_poll_has_empty_options(self) -> None:
        """Slides without a poll block have an empty poll_options list."""
        slides = parse_markdown(_POLL_MD)
        assert slides[0].poll_options == []
        assert slides[2].poll_options == []

    def test_poll_with_star_markers(self) -> None:
        """Poll options with ``*`` list markers are parsed correctly."""
        md = "# Poll\n\n<!-- poll\n* Option A\n* Option B\n-->\n"
        slides = parse_markdown(md)
        assert slides[0].poll_options == ["Option A", "Option B"]

    def test_poll_with_no_markers(self) -> None:
        """Poll options without list markers are parsed correctly."""
        md = "# Poll\n\n<!-- poll\nYes\nNo\n-->\n"
        slides = parse_markdown(md)
        assert slides[0].poll_options == ["Yes", "No"]

    def test_poll_with_blank_lines_inside(self) -> None:
        """Blank lines inside the poll block are ignored."""
        md = "# Poll\n\n<!-- poll\n- A\n\n- B\n-->\n"
        slides = parse_markdown(md)
        assert slides[0].poll_options == ["A", "B"]

    def test_no_poll_block_returns_empty(self) -> None:
        """Slides without any HTML comment return empty options."""
        md = "# Slide\n\nJust regular content.\n"
        slides = parse_markdown(md)
        assert slides[0].poll_options == []

    def test_poll_options_appear_in_api_response(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """The REST API returns poll_options for each slide."""
        resp = client.get("/api/presentations/demo/slides")
        assert resp.status_code == 200
        slides = resp.json()
        assert slides[1]["poll_options"] == ["Red", "Green", "Blue"]
        assert slides[0]["poll_options"] == []


# ---------------------------------------------------------------------------
# WebSocket poll lifecycle tests
# ---------------------------------------------------------------------------


class TestPollOpenedOnNavigate:
    """Tests for poll_opened messages on slide navigation."""

    def test_navigate_to_poll_slide_sends_poll_opened(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Navigating to a poll slide broadcasts ``poll_opened``."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                # Navigate to the poll slide (index 1).
                presenter_ws.send_json({"type": "navigate", "slide_index": 1})

                # Presenter receives poll_opened.
                poll_msg = presenter_ws.receive_json()
                assert poll_msg["type"] == "poll_opened"
                assert poll_msg["slide_index"] == 1
                assert poll_msg["options"] == ["Red", "Green", "Blue"]
                assert poll_msg["results"] == [0, 0, 0]

                # Audience receives slide_changed then poll_opened.
                slide_msg = audience_ws.receive_json()
                assert slide_msg["type"] in ("slide_changed", "poll_opened")
                poll_msg2 = audience_ws.receive_json()
                assert poll_msg2["type"] in ("slide_changed", "poll_opened")

    def test_navigate_away_from_poll_sends_poll_closed(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Navigating away from a poll slide broadcasts ``poll_closed``."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            # Navigate to poll slide.
            presenter_ws.send_json({"type": "navigate", "slide_index": 1})
            presenter_ws.receive_json()  # poll_opened

            # Navigate away from poll slide.
            presenter_ws.send_json({"type": "navigate", "slide_index": 2})
            closed_msg = presenter_ws.receive_json()
            assert closed_msg["type"] == "poll_closed"
            assert closed_msg["slide_index"] == 1
            assert closed_msg["options"] == ["Red", "Green", "Blue"]


# ---------------------------------------------------------------------------
# Poll vote tests
# ---------------------------------------------------------------------------


class TestPollVote:
    """Tests for audience poll voting."""

    def test_audience_can_vote(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An audience member can vote on an active poll."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                # Navigate to poll slide.
                presenter_ws.send_json({"type": "navigate", "slide_index": 1})

                # Drain poll_opened from both.
                presenter_ws.receive_json()  # poll_opened
                audience_ws.receive_json()  # slide_changed
                audience_ws.receive_json()  # poll_opened

                # Audience votes.
                audience_ws.send_json(
                    {
                        "type": "poll_vote",
                        "slide_index": 1,
                        "option_index": 0,
                    }
                )

                # Both should receive poll_results.
                results_p = presenter_ws.receive_json()
                assert results_p["type"] == "poll_results"
                assert results_p["results"] == [1, 0, 0]

                results_a = audience_ws.receive_json()
                assert results_a["type"] == "poll_results"
                assert results_a["results"] == [1, 0, 0]

    def test_duplicate_vote_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An audience member cannot vote twice on the same poll.

        The rate limiter (limit=1 for ``poll_vote``) fires before the
        handler's ``already_voted`` check, so the error code is
        ``rate_limited``.
        """
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                # Navigate to poll slide.
                presenter_ws.send_json({"type": "navigate", "slide_index": 1})
                presenter_ws.receive_json()  # poll_opened
                audience_ws.receive_json()  # slide_changed
                audience_ws.receive_json()  # poll_opened

                # First vote succeeds.
                audience_ws.send_json(
                    {
                        "type": "poll_vote",
                        "slide_index": 1,
                        "option_index": 1,
                    }
                )
                audience_ws.receive_json()  # poll_results
                presenter_ws.receive_json()  # poll_results

                # Second vote rejected by rate limiter (1 poll_vote per session).
                audience_ws.send_json(
                    {
                        "type": "poll_vote",
                        "slide_index": 1,
                        "option_index": 2,
                    }
                )
                error = audience_ws.receive_json()
                assert error["type"] == "error"
                assert error["code"] == "rate_limited"

    def test_vote_on_inactive_poll_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Voting on a slide that is not the active poll returns an error."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                # Don't navigate to poll slide — stay on slide 0.
                audience_ws.send_json(
                    {
                        "type": "poll_vote",
                        "slide_index": 1,
                        "option_index": 0,
                    }
                )

                error = audience_ws.receive_json()
                assert error["type"] == "error"
                assert error["code"] == "invalid_vote"

    def test_invalid_option_index_rejected(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Voting with an out-of-range option index returns an error."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                # Navigate to poll slide.
                presenter_ws.send_json({"type": "navigate", "slide_index": 1})
                presenter_ws.receive_json()  # poll_opened
                audience_ws.receive_json()  # slide_changed
                audience_ws.receive_json()  # poll_opened

                # Vote with invalid option.
                audience_ws.send_json(
                    {
                        "type": "poll_vote",
                        "slide_index": 1,
                        "option_index": 99,
                    }
                )
                error = audience_ws.receive_json()
                assert error["type"] == "error"
                assert error["code"] == "invalid_vote"

    def test_presenter_cannot_vote(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """A presenter is rejected when trying to vote."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            # Navigate to poll slide.
            presenter_ws.send_json({"type": "navigate", "slide_index": 1})
            presenter_ws.receive_json()  # poll_opened

            # Presenter tries to vote.
            presenter_ws.send_json(
                {
                    "type": "poll_vote",
                    "slide_index": 1,
                    "option_index": 0,
                }
            )
            error = presenter_ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "unauthorized"

    def test_multiple_audience_votes_accumulate(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Votes from different audience members accumulate correctly."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as aud1:
                aud1.receive_json()  # connected
                aud1.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                with client.websocket_connect("/ws/demo?role=audience") as aud2:
                    aud2.receive_json()  # connected
                    aud2.receive_json()  # peer_count
                    presenter_ws.receive_json()  # peer_count
                    aud1.receive_json()  # peer_count

                    # Navigate to poll slide.
                    presenter_ws.send_json({"type": "navigate", "slide_index": 1})
                    presenter_ws.receive_json()  # poll_opened
                    aud1.receive_json()  # slide_changed
                    aud1.receive_json()  # poll_opened
                    aud2.receive_json()  # slide_changed
                    aud2.receive_json()  # poll_opened

                    # Audience 1 votes for option 0.
                    aud1.send_json(
                        {
                            "type": "poll_vote",
                            "slide_index": 1,
                            "option_index": 0,
                        }
                    )
                    # Drain results from all.
                    presenter_ws.receive_json()  # poll_results
                    aud1.receive_json()  # poll_results
                    aud2.receive_json()  # poll_results

                    # Audience 2 votes for option 2.
                    aud2.send_json(
                        {
                            "type": "poll_vote",
                            "slide_index": 1,
                            "option_index": 2,
                        }
                    )
                    results = presenter_ws.receive_json()
                    assert results["type"] == "poll_results"
                    assert results["results"] == [1, 0, 1]


class TestPollStateOnConnect:
    """Tests that audience members receive active poll state on connect."""

    def test_audience_receives_poll_opened_on_connect(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An audience member joining while a poll is active gets poll_opened."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            # Navigate to poll slide before any audience joins.
            presenter_ws.send_json({"type": "navigate", "slide_index": 1})
            presenter_ws.receive_json()  # poll_opened

            # Now an audience member connects.
            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                connected = audience_ws.receive_json()
                assert connected["type"] == "connected"
                assert connected["current_slide"] == 1

                # Should receive poll_opened with initial results.
                poll_msg = audience_ws.receive_json()
                assert poll_msg["type"] == "poll_opened"
                assert poll_msg["slide_index"] == 1
                assert poll_msg["options"] == ["Red", "Green", "Blue"]
                assert poll_msg["results"] == [0, 0, 0]

    def test_audience_receives_poll_with_existing_votes_on_connect(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An audience member joining sees accumulated votes in poll_opened."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            # First audience member joins, navigates to poll, votes.
            with client.websocket_connect("/ws/demo?role=audience") as aud1:
                aud1.receive_json()  # connected
                aud1.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                presenter_ws.send_json({"type": "navigate", "slide_index": 1})
                presenter_ws.receive_json()  # poll_opened
                aud1.receive_json()  # slide_changed
                aud1.receive_json()  # poll_opened

                aud1.send_json(
                    {"type": "poll_vote", "slide_index": 1, "option_index": 0}
                )
                presenter_ws.receive_json()  # poll_results
                aud1.receive_json()  # poll_results

                # Second audience member joins while poll is active with votes.
                with client.websocket_connect("/ws/demo?role=audience") as aud2:
                    connected = aud2.receive_json()
                    assert connected["type"] == "connected"

                    poll_msg = aud2.receive_json()
                    assert poll_msg["type"] == "poll_opened"
                    assert poll_msg["slide_index"] == 1
                    assert poll_msg["options"] == ["Red", "Green", "Blue"]
                    assert poll_msg["results"] == [1, 0, 0]

    def test_no_poll_opened_on_non_poll_slide(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """An audience member joining on a non-poll slide gets no poll_opened."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            # Stay on slide 0 (not a poll slide).
            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                connected = audience_ws.receive_json()
                assert connected["type"] == "connected"

                # Next message should be peer_count, not poll_opened.
                peer_msg = audience_ws.receive_json()
                assert peer_msg["type"] == "peer_count"


class TestPollVotesPreservedAfterClose:
    """Tests that poll votes persist after navigating away and back."""

    def test_votes_preserved_when_returning_to_poll(
        self, client: TestClient, presentations_dir: Path
    ) -> None:
        """Returning to a poll slide shows previous votes in poll_opened."""
        with client.websocket_connect("/ws/demo?role=presenter") as presenter_ws:
            presenter_ws.receive_json()  # connected
            presenter_ws.receive_json()  # questions_list
            presenter_ws.receive_json()  # peer_count

            with client.websocket_connect("/ws/demo?role=audience") as audience_ws:
                audience_ws.receive_json()  # connected
                audience_ws.receive_json()  # peer_count
                presenter_ws.receive_json()  # peer_count

                # Navigate to poll and vote.
                presenter_ws.send_json({"type": "navigate", "slide_index": 1})
                presenter_ws.receive_json()  # poll_opened
                audience_ws.receive_json()  # slide_changed
                audience_ws.receive_json()  # poll_opened

                audience_ws.send_json(
                    {
                        "type": "poll_vote",
                        "slide_index": 1,
                        "option_index": 2,
                    }
                )
                presenter_ws.receive_json()  # poll_results
                audience_ws.receive_json()  # poll_results

                # Navigate away.
                presenter_ws.send_json({"type": "navigate", "slide_index": 2})
                presenter_ws.receive_json()  # poll_closed
                audience_ws.receive_json()  # slide_changed
                audience_ws.receive_json()  # poll_closed

                # Navigate back to poll.
                presenter_ws.send_json({"type": "navigate", "slide_index": 1})
                poll_msg = presenter_ws.receive_json()
                assert poll_msg["type"] == "poll_opened"
                assert poll_msg["results"] == [0, 0, 1]
