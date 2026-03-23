# Interactive Presenter

Turn any Markdown file into a live, interactive presentation. The audience
joins from their phones via QR code and can send emoji reactions, vote in
polls, and ask questions -- all in real time.

## Quick Start

```bash
./dev.sh
```

This installs dependencies (if needed) and starts both servers:

| Service  | URL                                                  |
|----------|------------------------------------------------------|
| Backend  | http://localhost:8000                                |
| Frontend | http://localhost:5173                                |
| Presenter| http://localhost:5173/presentations/demo             |
| Audience | http://localhost:5173/presentations/demo/audience    |

Stop with `Ctrl+C` or `./dev.sh stop`.

### Prerequisites

- Python 3.11+
- Node.js 18+ with npm

### Manual Setup

If you prefer running things yourself:

```bash
# Backend
pip install -e .
python -m backend.main          # http://localhost:8000

# Frontend (separate terminal)
cd frontend && npm install
npm run dev -- --host            # http://localhost:5173
```

## How It Works

1. Write your presentation as a Markdown file (H1 headings = slide breaks)
2. Drop it in `presentations/`
3. Open the presenter view -- navigate with arrow keys
4. The first slide shows a QR code; audience scans to join
5. Audience can react, vote on polls, and ask questions in real time

### Writing Slides

```markdown
# Welcome

This is the first slide. A QR code appears here automatically.

# Agenda

- Item one
- Item two

# Audience Poll

<!-- poll
What's your favorite color?
- Red
- Blue
- Green
-->
```

### Keyboard Shortcuts (Presenter)

| Key              | Action                |
|------------------|-----------------------|
| Right / Space    | Next slide            |
| Left             | Previous slide        |
| Q                | Toggle Q&A panel      |

## Architecture

**Backend:** Python / FastAPI / Uvicorn with WebSocket support
**Frontend:** React 19 / TypeScript / Vite
**Database:** None yet (in-memory state; SQLite planned)
**Communication:** WebSocket rooms (one per presentation)

```
backend/
  main.py                  # FastAPI app entry point
  routes.py                # REST API (presentations, slides)
  parser.py                # Markdown -> slides + poll extraction
  ws/
    handlers.py            # WebSocket message dispatch
    connection_manager.py  # Room state (connections, polls, questions)
    models.py              # Pydantic message schemas
    rate_limiter.py        # Per-connection rate limiting

frontend/src/
  components/
    SlideViewer.tsx         # Presenter full-screen view
    AudienceView.tsx        # Audience companion page
    PollCard.tsx            # Audience poll voting
    PollOverlay.tsx         # Presenter poll results
    EmojiReactionBar.tsx    # Audience emoji picker
    ReactionOverlay.tsx     # Floating emoji particles
    QRCodeOverlay.tsx       # QR code on first slide
  hooks/
    useWebSocket.ts         # Connection lifecycle + reconnect
    useQuestions.ts          # Q&A state
    usePolls.ts             # Poll state
    useReactions.ts         # Reaction particles
```

## Feature Specs

Detailed specifications live in `spec/`:

- [Mission Statement](spec/mission_statement.md) -- what and why
- [Tech Stack](spec/tech_stack.md) -- technology choices
- [Slide Viewer](spec/slide_viewer.md) -- parser, REST API, navigation
- [WebSocket Infrastructure](spec/websocket_infrastructure.md) -- rooms, protocol, reconnection
- [Emoji Reactions](spec/emoji_reactions.md) -- allowlist, rate limits, animation
- [Polls](spec/polls.md) -- markdown syntax, vote lifecycle, results
- [Q&A](spec/qa.md) -- question submission, presenter panel, slide context
- [QR Code](spec/qr_code.md) -- join flow, component design

## Blog

Development chronicles:

- [Episode 01](blog/episode_01.org) -- Project inception
- [Episode 02](blog/episode_02.org) -- Building the slide viewer
- [Episode 03](blog/episode_03.org) -- The parser bug
- [Episode 04](blog/episode_04.org) -- Four features, multi-agent workflow
- [Episode 05](blog/episode_05.org) -- Hardening and polish
- [Episode 06](blog/episode_06.org) -- Production-ready and presentation-ready

## Running Tests

```bash
# Backend tests
pytest

# Frontend type check
cd frontend && npx tsc -b

# Frontend build
cd frontend && npm run build

# Lint
ruff check .
ruff format --check .
```

## License

Private project.
