# Slide Viewer v1 — Feature Specification

## Overview

The Slide Viewer is the first building block of the Interactive Presenter. It lets
a presenter load a Markdown file and navigate through its slides in a clean,
full-screen view. No audience interaction yet — that comes in later features.

---

## Presentation Format

Presentations are plain `.md` files stored on disk. Each **H1 heading (`# `)**
marks the start of a new slide. Everything between two H1 headings (or between
the last H1 and end-of-file) is the body of that slide.

**Parsing rules:**
- Lines before the first `# ` are ignored.
- The H1 text becomes the slide `title`; the remaining lines become `content`.
- Trailing whitespace is stripped from both fields.

---

## Backend

### Runtime & Framework
Python 3.11+, FastAPI, Uvicorn.

### Presentations Storage
- Presentations are `.md` files inside a configurable directory.
- Default path: `presentations/` at the repo root.
- Controlled by the environment variable `PRESENTATIONS_DIR`.
- No database is used in this version — files are read from disk on every request.

### Data Models

**Presentation**

| Field   | Type   | Description                               |
|---------|--------|-------------------------------------------|
| `id`    | string | Filename without extension (e.g. `demo`)  |
| `title` | string | Text of the first H1 found in the file    |

**Slide**

| Field     | Type   | Description                                    |
|-----------|--------|------------------------------------------------|
| `index`   | int    | Zero-based position in the presentation        |
| `title`   | string | H1 heading text for this slide                 |
| `content` | string | Raw Markdown body below the H1 (may be empty)  |

### API Endpoints

#### `GET /api/presentations`
Returns all presentations discovered in `PRESENTATIONS_DIR`.

**Response `200 OK`:**
```json
[
  { "id": "demo", "title": "Welcome to Interactive Presenter" }
]
```

#### `GET /api/presentations/{id}/slides`
Reads `{id}.md`, parses it, and returns the slide list.

**Response `200 OK`:**
```json
[
  {
    "index": 0,
    "title": "Welcome to Interactive Presenter",
    "content": "Subtitle or intro text here."
  },
  {
    "index": 1,
    "title": "What is this?",
    "content": "A **Markdown-driven** presentation tool."
  }
]
```

**Response `404 Not Found`:**
```json
{ "detail": "Presentation not found" }
```

### CORS
Enable CORS for all origins during development so the Vite dev server
(default port 5173) can reach the API. In production, restrict to known origins.

### Entry Point
`python -m backend.main` — starts Uvicorn on `http://localhost:8000`.

---

## Frontend

### Runtime & Tooling
React 18 + TypeScript, scaffolded with Vite. Dev server runs on
`http://localhost:5173`.

### Routes

| Route                   | Component          | Description                      |
|-------------------------|--------------------|----------------------------------|
| `/`                     | `PresentationList` | Lists available presentations    |
| `/presentations/:id`    | `SlideViewer`      | Full-screen slide viewer         |

### `PresentationList` Component
- On mount, fetches `GET /api/presentations`.
- Renders a clickable list of presentation titles.
- Clicking a title navigates to `/presentations/:id`.

### `SlideViewer` Component
- On mount, fetches `GET /api/presentations/:id/slides`.
- Displays one slide at a time in a full-viewport layout.
- Renders slide `content` as HTML via a Markdown rendering library (e.g.
  `react-markdown`).
- Shows a **slide counter** in the bottom-right corner: `"3 / 12"`
  (1-based current index / total count).

### Keyboard Navigation

| Key          | Action                             |
|--------------|------------------------------------|
| `ArrowRight` | Advance to the next slide          |
| `Space`      | Advance to the next slide          |
| `ArrowLeft`  | Go back to the previous slide      |

Navigation clamps at the boundaries — no wrap-around.

### Visual Design
- Full-viewport layout; no toolbars, sidebars, or chrome.
- Dark background (`#1a1a1a` or equivalent).
- Light text (`#f0f0f0`).
- Slide `title` rendered as a large heading (e.g. `h1` or `h2` element).
- Body text at a comfortable reading size (≥ 1.25rem).
- Slide counter in the bottom-right corner, muted/subdued color.
- Legible on a 1080p display at full screen.

---

## Sample Presentation — `presentations/demo.md`

Include a file with 4–5 slides that demonstrates the supported format:

1. **Title slide** — H1 only, no body content.
2. **Bullet list slide** — unordered list items.
3. **Rich text slide** — uses **bold** and *italic* inline formatting.
4. **Code slide** — contains a fenced code block.
5. *(Optional)* **Closing slide** — simple call-to-action or thank-you.

---

## Out of Scope for v1

- Database persistence (no SQLite yet)
- QR code generation on the first slide (planned for v2)
- Audience reactions, polls, and Q&A
- Slide thumbnails or overview panel
- Presenter notes
- Authentication or multi-user sessions
