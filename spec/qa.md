# Q&A (Audience Questions) — Feature Specification

## Overview

The Q&A feature lets audience members submit text questions at any point during
a presentation. Each question is automatically tagged with the slide that was
active when it was asked, giving the presenter spatial context when reviewing
them later.

Questions flow from audience to presenter over the existing WebSocket
infrastructure. The presenter is notified in real time as questions arrive via
a question count badge in the slide footer. A dedicated Q&A panel — toggled by
pressing `Q` — lists all questions grouped by slide so the presenter can work
through them at the end.

This feature is entirely in-memory for v1. There is no database persistence,
no question moderation, and no upvoting.

---

## Architecture

```
┌──────────────────┐  question_submit   ┌─────────────────┐
│  Audience View   │───────────────────►│  FastAPI Server  │
│  (AudienceView)  │                    │  (handlers.py)   │
│                  │◄───────────────────│                  │
│  Question form   │  question_received │  _Room.questions │
│  + count badge   │  (confirmation)    │  (in-memory)     │
└──────────────────┘                    └────────┬────────┘
                                                 │ question_received
                                                 │ (new question notification)
                                        ┌────────▼────────┐
                                        │  Presenter View  │
                                        │  (SlideViewer)   │
                                        │  Badge + Q panel │
                                        └─────────────────┘

                                        questions_list (on demand)
                                        ◄──────────────────────────
                                        get_questions (presenter →)
```

The Q&A messages ride the same WebSocket connection established by the
infrastructure spec. No new endpoints or connections are needed.

---

## Entities

### Question

A question submitted by a single audience member during a live presentation.

| Field         | Type     | Constraints                                           |
|---------------|----------|-------------------------------------------------------|
| `id`          | string   | Server-generated UUID v4; unique within the room      |
| `text`        | string   | 1–280 characters after trimming; must not be empty    |
| `slide_index` | integer  | Zero-based index of the slide active at submit time   |
| `timestamp`   | string   | ISO 8601 UTC datetime, set by the server on receipt   |

Questions are **anonymous** — no submitter identity is stored or transmitted.
The room retains all questions for the duration of the session; they are
discarded when the room is destroyed (after the grace period).

---

## Message Protocol

All messages follow the standard envelope defined in
`websocket_infrastructure.md`:

```json
{
  "type": "<message_type>",
  "timestamp": "<ISO 8601 UTC>",
  ...payload fields
}
```

### Client → Server

#### `question_submit` (audience only)

An audience member submits a question.

```json
{
  "type": "question_submit",
  "timestamp": "2026-03-20T14:05:10Z",
  "text": "How does this scale beyond 10,000 users?"
}
```

| Field       | Type   | Required | Constraints                               |
|-------------|--------|----------|-------------------------------------------|
| `type`      | string | yes      | Must equal `"question_submit"`            |
| `timestamp` | string | yes      | ISO 8601; provided by the client          |
| `text`      | string | yes      | 1–280 chars after trimming whitespace     |

**Role enforcement:** If a presenter sends `question_submit`, the server
responds with `error` (`"unauthorized"`). Only audience members may submit.

**Slide tagging:** The server reads `room.current_slide` at the moment of
receipt and stores it on the question. The client does not send a slide index —
the server is the authority on which slide is active.

#### `get_questions` (presenter only)

The presenter requests the full list of questions on demand. Sent when the
presenter opens the Q&A panel after questions may already have accumulated
(e.g., after reconnecting).

```json
{
  "type": "get_questions",
  "timestamp": "2026-03-20T14:10:00Z"
}
```

| Field       | Type   | Required | Constraints                      |
|-------------|--------|----------|----------------------------------|
| `type`      | string | yes      | Must equal `"get_questions"`     |
| `timestamp` | string | yes      | ISO 8601; provided by the client |

**Role enforcement:** If an audience member sends `get_questions`, the server
responds with `error` (`"unauthorized"`).

The server responds immediately with a `questions_list` message sent only to
the requesting presenter.

### Server → Client

#### `question_received`

Sent by the server in two contexts:

1. **To the submitter** — confirms their question was accepted (a personal acknowledgement).
2. **To the presenter** — notifies them a new question arrived.

The payload is the same for both recipients.

```json
{
  "type": "question_received",
  "timestamp": "2026-03-20T14:05:10Z",
  "question": {
    "id": "a3f8c1d2-4b5e-4f6a-8c9d-0e1f2a3b4c5d",
    "text": "How does this scale beyond 10,000 users?",
    "slide_index": 3,
    "timestamp": "2026-03-20T14:05:10Z"
  }
}
```

| Field               | Type    | Description                                       |
|---------------------|---------|---------------------------------------------------|
| `type`              | string  | Always `"question_received"`                      |
| `timestamp`         | string  | ISO 8601 UTC; when the server processed it        |
| `question.id`       | string  | Server-generated UUID                             |
| `question.text`     | string  | The sanitized question text                       |
| `question.slide_index` | int  | Slide that was active when the question arrived   |
| `question.timestamp`| string  | ISO 8601 UTC; same as the outer `timestamp`       |

The submitter uses this to show a confirmation message. The presenter uses this
to increment the badge count and prepend the question to the Q&A panel.

**Who receives it:**
- The submitting audience connection (confirmation).
- The presenter connection, if one is connected to the room.

Audience members other than the submitter do **not** receive `question_received`.

#### `questions_list`

Sent to the presenter only, in response to `get_questions` or automatically
during the presenter's `connected` handshake (if questions already exist in
the room at the time the presenter connects or reconnects).

```json
{
  "type": "questions_list",
  "timestamp": "2026-03-20T14:10:00Z",
  "questions": [
    {
      "id": "a3f8c1d2-4b5e-4f6a-8c9d-0e1f2a3b4c5d",
      "text": "How does this scale beyond 10,000 users?",
      "slide_index": 3,
      "timestamp": "2026-03-20T14:05:10Z"
    },
    {
      "id": "b4e9d2e3-5c6f-4g7b-9d0e-1f2g3h4i5j6k",
      "text": "What is the latency at the edge?",
      "slide_index": 3,
      "timestamp": "2026-03-20T14:07:22Z"
    }
  ]
}
```

| Field              | Type            | Description                               |
|--------------------|-----------------|-------------------------------------------|
| `type`             | string          | Always `"questions_list"`                 |
| `timestamp`        | string          | ISO 8601 UTC; when the list was generated |
| `questions`        | array           | All questions in the room, ordered by     |
|                    |                 | ascending `timestamp` (oldest first)      |
| `questions[n]`     | Question object | Same schema as in `question_received`     |

If no questions have been asked, `questions` is an empty array `[]`.

---

## Question State in Room Memory

The `_Room` dataclass gains a new field:

| Field       | Type             | Description                                              |
|-------------|------------------|----------------------------------------------------------|
| `questions` | list[Question]   | All questions submitted to this room, in arrival order   |

Questions are appended as they arrive and are never removed during the session.
The list is cleared when the room is destroyed at the end of the grace period.

A `Question` is a plain data object (no WebSocket-specific logic):

| Field         | Type | Description                                      |
|---------------|------|--------------------------------------------------|
| `id`          | str  | UUID v4, generated by the server on submission   |
| `text`        | str  | Sanitized question text                          |
| `slide_index` | int  | `room.current_slide` at the moment of receipt    |
| `timestamp`   | str  | ISO 8601 UTC string, set by the server           |

---

## Backend Implementation

### New Models (`backend/ws/models.py`)

Three new models are required.

#### `QuestionData` (shared sub-object)

Used inside both `question_received` and `questions_list` payloads.

```
QuestionData
  id:          str   — UUID v4
  text:        str   — sanitized question text
  slide_index: int   — zero-based slide index
  timestamp:   str   — ISO 8601 UTC
```

#### `QuestionSubmitMessage` (client → server)

Validates incoming `question_submit` messages.

```
QuestionSubmitMessage
  type:      str   — must equal "question_submit"
  timestamp: str   — ISO 8601 UTC
  text:      str   — 1–280 characters after strip()
```

Validation rules enforced by the model:
- `text.strip()` must have length ≥ 1 (not blank).
- `text` length after stripping must be ≤ 280 characters.
- A `validator` (or `field_validator`) should strip leading/trailing whitespace
  before length checks so the stored value is already trimmed.

#### `GetQuestionsMessage` (client → server)

Validates incoming `get_questions` messages.

```
GetQuestionsMessage
  type:      str   — must equal "get_questions"
  timestamp: str   — ISO 8601 UTC
```

No additional payload fields.

#### `QuestionReceivedPayload` (server → client)

```
QuestionReceivedPayload
  type:      str          — always "question_received"
  timestamp: str          — ISO 8601 UTC (default: now)
  question:  QuestionData
```

#### `QuestionsListPayload` (server → client)

```
QuestionsListPayload
  type:      str                — always "questions_list"
  timestamp: str                — ISO 8601 UTC (default: now)
  questions: list[QuestionData] — ordered by ascending timestamp
```

### Room State (`backend/ws/connection_manager.py`)

Add `questions: list[QuestionData]` to the `_Room` dataclass, defaulting to an
empty list.

```
_Room
  ...existing fields...
  questions: list[QuestionData]   default = []
```

No other changes to `ConnectionManager` are required. The handler reads
`room.current_slide` and appends to `room.questions` directly.

Additionally, extend the `connected` handshake: after sending `ConnectedPayload`
to a newly connected **presenter**, also send a `QuestionsListPayload` (even if
it is empty). This ensures a reconnecting presenter immediately knows the current
question state without having to send `get_questions`.

### Message Dispatch (`backend/ws/handlers.py`)

Extend `_dispatch` with two new branches:

#### `question_submit` branch

```
1. Check role == "audience". If not, send error("unauthorized").
2. Parse with QuestionSubmitMessage(**data).
   On ValidationError → send error("invalid_message", detail=str(exc)).
3. Retrieve room = manager.get_room(presentation_id). If None, return.
4. Generate id = str(uuid.uuid4()).
5. Build QuestionData:
     id          = generated uuid
     text        = validated message text (already stripped)
     slide_index = room.current_slide
     timestamp   = current UTC ISO 8601 string
6. Append QuestionData to room.questions.
7. Build QuestionReceivedPayload(question=question_data).
8. Send payload to the submitting websocket (confirmation).
9. If room.presenter is not None:
     Send payload to room.presenter.websocket (notification).
```

#### `get_questions` branch

```
1. Check role == "presenter". If not, send error("unauthorized").
2. Parse with GetQuestionsMessage(**data).
   On ValidationError → send error("invalid_message", detail=str(exc)).
3. Retrieve room = manager.get_room(presentation_id). If None, return.
4. Build QuestionsListPayload(questions=room.questions).
5. Send payload to the requesting websocket only.
```

#### Presenter connect handshake extension

In `ConnectionManager.connect`, after sending `ConnectedPayload` to a
newly connecting **presenter**, immediately send a `QuestionsListPayload`
containing the current `room.questions`:

```
if role == "presenter":
    questions_list = QuestionsListPayload(questions=room.questions)
    await websocket.send_json(questions_list.model_dump())
```

This is fire-and-forget: the presenter may have zero questions on first connect,
but the message is sent regardless to establish a consistent initial state.

### Rate Limiting

No changes required. The `RateLimiter` already enforces
**3 `question_submit` messages per 60 seconds** per connection. This limit
is already configured in `rate_limiter.py`:

```
"question_submit": _WindowConfig(limit=3, window_seconds=60.0)
```

When the rate limit is hit, the existing `rate_limited` error response is sent
to the client. The frontend should display a user-facing message in this case
(see Frontend section).

---

## Frontend Implementation

### TypeScript Types (`frontend/src/types.ts`)

Add the following to the existing type file.

#### New shared sub-type

```typescript
/** A single audience question, as returned by the server. */
export interface Question {
  id: string;
  text: string;
  slide_index: number;
  timestamp: string;
}
```

#### New server → client message types

```typescript
/** Server → Client: confirms question submission to submitter; notifies presenter. */
export interface QuestionReceivedMessage {
  type: 'question_received';
  timestamp: string;
  question: Question;
}

/** Server → Client: full list of questions in the room, sent to presenter. */
export interface QuestionsListMessage {
  type: 'questions_list';
  timestamp: string;
  questions: Question[];
}
```

#### New client → server message types

```typescript
/** Client → Server: audience submits a question. */
export interface QuestionSubmitMessage {
  type: 'question_submit';
  timestamp: string;
  text: string;
}

/** Client → Server: presenter requests the full question list. */
export interface GetQuestionsMessage {
  type: 'get_questions';
  timestamp: string;
}
```

#### Union type extensions

Extend `ServerMessage` and `ClientMessage`:

```typescript
export type ServerMessage =
  | ConnectedMessage
  | SlideChangedMessage
  | PeerCountMessage
  | ErrorMessage
  | PongMessage
  | QuestionReceivedMessage   // ← new
  | QuestionsListMessage;     // ← new

export type ClientMessage =
  | NavigateMessage
  | PingMessage
  | QuestionSubmitMessage     // ← new
  | GetQuestionsMessage;      // ← new
```

### `useQuestions` Hook

A new custom hook that manages the local question list and submission logic.
Located at `frontend/src/hooks/useQuestions.ts`.

```typescript
interface UseQuestionsOptions {
  send: (message: ClientMessage) => void;
  isConnected: boolean;
}

interface UseQuestionsReturn {
  questions: Question[];           // full list, maintained locally
  questionCount: number;           // questions.length
  submitQuestion: (text: string) => void;
  isSubmitting: boolean;           // true between send and confirmation
  lastSubmitError: string | null;  // set on rate_limited or validation error
  clearSubmitError: () => void;
  handleMessage: (message: ServerMessage) => void; // call from onMessage
}

function useQuestions(options: UseQuestionsOptions): UseQuestionsReturn;
```

#### Internal State

| State field       | Type              | Description                                         |
|-------------------|-------------------|-----------------------------------------------------|
| `questions`       | `Question[]`      | All questions received, in arrival order            |
| `isSubmitting`    | `boolean`         | Optimistic lock: true from submit until confirmation |
| `lastSubmitError` | `string \| null`  | Human-readable error from last failed submit        |

#### `handleMessage` logic

Called by the parent component's `onMessage` callback (passed to `useWebSocket`).

```
on "questions_list":   replace questions state with message.questions

on "question_received": append message.question to questions state
                        if isSubmitting was true, set isSubmitting = false
                        (the confirmation for our own submission arrived)

on "error" where code == "rate_limited":
                        set isSubmitting = false
                        set lastSubmitError = "You're sending questions too fast.
                                              Wait a moment and try again."

on "error" where code == "invalid_message":
                        set isSubmitting = false
                        set lastSubmitError = "Question could not be submitted."
```

#### `submitQuestion` logic

```
1. Trim text.
2. If text.length == 0 or text.length > 280 → set lastSubmitError, return.
3. If !isConnected → set lastSubmitError = "Not connected.", return.
4. If isSubmitting → return (debounce double-tap).
5. Set isSubmitting = true, clearSubmitError.
6. Call send({ type: "question_submit", timestamp: now, text: trimmed }).
7. Set a fallback timeout of 10 seconds:
     if isSubmitting is still true after 10s, set isSubmitting = false
     and set lastSubmitError = "Question may not have been received."
```

The 10-second fallback prevents the UI from getting stuck in a submitting state
if the server drops the confirmation.

### Audience View (`frontend/src/components/AudienceView.tsx`)

#### Question Input Form

Add a fixed form at the bottom of the audience view. The form should not
obstruct the slide content — it sits in a footer bar, overlaid above the
`slide-footer` area.

**Structure:**

```
[Question input form]
┌──────────────────────────────────────────────────────────────────────────┐
│  ┌───────────────────────────────────────────────────────┐  [ Ask ]     │
│  │ Ask a question…                          (char count) │              │
│  └───────────────────────────────────────────────────────┘              │
│  ← error message or confirmation here (conditionally rendered)          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Behaviour:**

- The textarea/input accepts free text up to 280 characters.
- Character count is displayed as `N / 280`. The count turns red (or a warning
  colour) when `N >= 260`.
- Submitting via the button or pressing `Enter` (without `Shift`) calls
  `submitQuestion`.
- While `isSubmitting` is true: the input and button are disabled; the button
  shows a loading indicator (e.g., a spinner or "Sending…" label).
- On successful confirmation (`isSubmitting` transitions back to false with no
  error):
  - Clear the text input.
  - Show a transient inline confirmation: "Question received ✓". This
    confirmation disappears after **3 seconds** or when the user starts typing
    again, whichever comes first.
- If `lastSubmitError` is set, display it in red below the input. It is cleared
  when the user starts typing.
- If not connected (`!isConnected`), disable the input and button and show a
  note: "Connect to ask questions."

**Question count:**

Show a small status line above or near the input:
- If `questionCount == 0`: nothing shown (no clutter for unused feature).
- If `questionCount >= 1`: "N question(s) asked so far" in a muted colour.

This gives audience members a sense of community engagement without revealing
other questions.

### Presenter View (`frontend/src/components/SlideViewer.tsx`)

#### Question Badge

In the existing `slide-footer`, add a question count badge to the right side of
the footer (between the slide counter and the WS status area).

```
[slide footer]
slide counter          [Q badge]          ws status
```

The badge appears only when `questionCount > 0`. It shows the question count
as a number inside a small pill/badge element with a label:
- Example: `❓ 5` or `5 questions`

The badge is a clickable button that toggles the Q&A panel open/closed.
Pressing `Q` on the keyboard also toggles the panel.

When new questions arrive while the panel is closed, the badge should briefly
animate (e.g., a short scale pulse) to draw the presenter's eye without being
disruptive.

#### Q&A Panel

A toggleable overlay/sidebar that lists all questions. Default state: **closed**.

**Layout:**

```
┌──────────────────────────────────────────────────────┐
│  Q&A   (12 questions)                          [✕]   │  ← Panel header
├──────────────────────────────────────────────────────┤
│  Slide 1 — Introduction                              │  ← Slide group header
│  ┌────────────────────────────────────────────────┐  │
│  │  "What is the core thesis?"            14:02   │  │  ← Question card
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  "Is there a recording?"               14:04   │  │
│  └────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────┤
│  Slide 3 — Architecture                              │
│  ┌────────────────────────────────────────────────┐  │
│  │  "How does this scale…?"               14:05   │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**Grouping:** Questions are grouped by `slide_index`, displayed in slide order
(ascending). Within each group, questions are in arrival order (ascending
`timestamp`). The slide group header shows "Slide N" or the slide title if
the presenter's local slides array is accessible.

**Timestamps:** Each card shows the question's timestamp formatted as `HH:MM`
in local time (for quick scanning), e.g. `14:05`.

**Empty state:** When no questions have been asked, the panel body shows:
"No questions yet. Audience members can ask questions from their companion page."

**Panel positioning:** Fixed overlay on the right side of the screen, covering
roughly the right 30–35% of the viewport. The slide content remains visible
(albeit partially covered) so the presenter does not lose their place. The
panel sits above the `slide-viewer` via `z-index`.

**Dismissal:**
- Press `Q` again.
- Click the `✕` close button in the panel header.
- Press `Escape`.

**`get_questions` on open:** When the presenter opens the panel, the frontend
sends `get_questions` to ensure the list is fresh. This covers the edge case
where the presenter connected before any audience member joined and then
questions arrived. (The `connected` handshake also sends the list, so this is a
belt-and-suspenders refresh.)

#### Keyboard shortcut registration

Add `Q` to the existing `keydown` handler in `SlideViewer`:

```
'ArrowRight' or ' ' → next slide  (existing)
'ArrowLeft'         → prev slide  (existing)
'Q'                 → toggle Q&A panel  (new)
'Escape'            → close Q&A panel if open, otherwise no-op  (new)
```

---

## Visual Design

### Design Tokens (consistent with existing palette)

The UI inherits the app's dark theme:

| Token                | Value            | Usage                               |
|----------------------|------------------|-------------------------------------|
| Background (dark)    | `#1a1a1a`        | App background                      |
| Surface              | `#252525`        | Panel background, card background   |
| Surface elevated     | `#2d2d2d`        | Card hover, input background        |
| Border               | `#333`           | Panel edge, card border             |
| Border hover         | `#555`           | Interactive elements on hover       |
| Text primary         | `#f0f0f0`        | Main question text                  |
| Text muted           | `#888`           | Timestamps, group headers, count    |
| Text danger          | `#f87171`        | Char-count warning, error messages  |
| Text success         | `#4ade80`        | Submission confirmation             |
| Accent (badge)       | `#fbbf24`        | Question badge pill                 |
| Focus ring           | `rgba(255,255,255,0.2)` | Keyboard focus outlines      |

### Audience Question Form

```css
/* Outer container — fixed footer bar */
.qa-form-container {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background-color: rgba(26, 26, 26, 0.95);
  border-top: 1px solid #333;
  padding: 0.75rem 1.25rem;
  z-index: 50;
}

/* Flex row: input + button */
.qa-form {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
  max-width: 720px;
  margin: 0 auto;
}

/* Text input */
.qa-input {
  flex: 1;
  background-color: #2d2d2d;
  border: 1px solid #333;
  border-radius: 6px;
  color: #f0f0f0;
  font-size: 1rem;
  padding: 0.5rem 0.75rem;
  resize: none;
  min-height: 2.5rem;
  max-height: 6rem;
}

.qa-input:focus {
  outline: none;
  border-color: #555;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.1);
}

.qa-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Submit button */
.qa-submit-btn {
  background-color: #333;
  border: 1px solid #555;
  border-radius: 6px;
  color: #f0f0f0;
  font-size: 0.9rem;
  padding: 0.5rem 1rem;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.qa-submit-btn:hover:not(:disabled) {
  background-color: #444;
  border-color: #888;
}

.qa-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Character counter */
.qa-char-count {
  font-size: 0.75rem;
  color: #666;
  text-align: right;
  margin-top: 0.25rem;
}

.qa-char-count.qa-char-count--warning {
  color: #fbbf24;
}

.qa-char-count.qa-char-count--danger {
  color: #f87171;
}

/* Feedback messages */
.qa-feedback {
  font-size: 0.8rem;
  margin-top: 0.25rem;
  text-align: center;
}

.qa-feedback--success {
  color: #4ade80;
}

.qa-feedback--error {
  color: #f87171;
}

/* Question count above form */
.qa-audience-count {
  font-size: 0.8rem;
  color: #666;
  text-align: center;
  margin-bottom: 0.5rem;
}
```

### Presenter Question Badge

```css
/* Badge button in slide footer */
.qa-badge-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background-color: transparent;
  border: 1px solid #444;
  border-radius: 12px;
  color: #fbbf24;
  font-size: 0.8rem;
  padding: 0.2em 0.6em;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.qa-badge-btn:hover {
  background-color: rgba(251, 191, 36, 0.1);
  border-color: #fbbf24;
}

/* Pulse animation when a new question arrives (add/remove class) */
@keyframes qa-badge-pop {
  0%   { transform: scale(1); }
  40%  { transform: scale(1.25); }
  100% { transform: scale(1); }
}

.qa-badge-btn--new {
  animation: qa-badge-pop 0.35s ease-out;
}
```

### Q&A Panel

```css
/* Slide-over panel */
.qa-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(400px, 35vw);
  background-color: #252525;
  border-left: 1px solid #333;
  display: flex;
  flex-direction: column;
  z-index: 200;
  overflow: hidden;
}

/* Panel header */
.qa-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.qa-panel-title {
  font-size: 1rem;
  font-weight: 600;
  color: #f0f0f0;
}

.qa-panel-count {
  font-size: 0.85rem;
  color: #888;
  margin-left: 0.5rem;
}

.qa-panel-close-btn {
  background: none;
  border: none;
  color: #888;
  font-size: 1.25rem;
  cursor: pointer;
  padding: 0.2em 0.4em;
  border-radius: 4px;
  line-height: 1;
  transition: color 0.15s ease;
}

.qa-panel-close-btn:hover {
  color: #f0f0f0;
}

/* Scrollable question list */
.qa-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem 1rem;
}

/* Slide group section */
.qa-slide-group {
  margin-bottom: 1.25rem;
}

.qa-slide-group-header {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #666;
  margin-bottom: 0.5rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid #2d2d2d;
}

/* Individual question card */
.qa-question-card {
  background-color: #2d2d2d;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.5rem;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
}

.qa-question-text {
  font-size: 0.9rem;
  color: #e0e0e0;
  line-height: 1.5;
  flex: 1;
}

.qa-question-time {
  font-size: 0.75rem;
  color: #666;
  white-space: nowrap;
  flex-shrink: 0;
  padding-top: 0.1rem;
}

/* Empty state */
.qa-panel-empty {
  color: #555;
  font-size: 0.9rem;
  text-align: center;
  padding: 2rem 1rem;
  line-height: 1.6;
}
```

---

## Content Validation

Validation happens at two layers: client-side (UX) and server-side (enforcement).
Server-side is authoritative.

### Client-Side (pre-send)

| Check                         | Behaviour                                               |
|-------------------------------|---------------------------------------------------------|
| Text is blank after trim      | Disable submit button; no error shown until submit attempted |
| Text length > 280             | Show character count in danger colour; disable submit button |
| Not connected                 | Disable form; show "Connect to ask questions."          |
| Already submitting            | Disable form; button shows "Sending…"                  |

### Server-Side (authoritative)

| Check                            | Error response                                           |
|----------------------------------|----------------------------------------------------------|
| Role is not `audience`           | `error("unauthorized", "Only audience can submit questions")` |
| `text` field missing             | `error("invalid_message", Pydantic validation detail)`  |
| `text.strip()` is empty          | `error("invalid_message", "Question text cannot be empty")` |
| `text.strip()` length > 280      | `error("invalid_message", "Question exceeds 280 characters")` |
| Rate limit exceeded (3 / 60s)    | `error("rate_limited", "Too many messages, slow down")` |

### Sanitization

The server stores `text.strip()` as the canonical question text. No HTML or
markdown rendering occurs — question text is displayed as plain text on the
presenter panel. The frontend should render it as plain text (not `innerHTML`)
to prevent XSS.

---

## Rate Limiting

The rate limiter already supports `question_submit` at **3 messages per 60-
second sliding window** per connection. This is defined in `rate_limiter.py`
and requires no changes.

The intent of the limit: a single audience member can ask 3 questions in a
minute, which is generous for normal use but prevents bulk spamming.

When the limit is hit:
- Server sends `error("rate_limited", ...)` to the submitter.
- The `useQuestions` hook catches this error code and sets `lastSubmitError`
  to a human-friendly message.
- The frontend shows the error message below the question input.
- The question form is re-enabled immediately (the user is not locked out —
  they just need to wait before the next successful submit).

The `get_questions` message falls under the catch-all `_DEFAULT_LIMIT`
(30 messages / 10 seconds), which is more than sufficient for this use case.

---

## Dependencies

### What this feature depends on

- **WebSocket Infrastructure** (`websocket_infrastructure.md`): Room model,
  `ConnectionManager`, message envelope, `_dispatch` function, rate limiter,
  `useWebSocket` hook, `ClientMessage` / `ServerMessage` union types.
- **Slide state**: `room.current_slide` (already maintained by the navigate
  handler) is used to tag questions.

### What depends on this feature

Nothing in v1. The Q&A system is self-contained.

---

## Testing Strategy

### Backend

All tests go in `tests/test_ws.py` alongside existing infrastructure tests,
or in a new `tests/test_ws_qa.py` if the file grows unwieldy.

#### Handler unit tests (via `TestClient.websocket_connect`)

| Test                                    | Precondition           | Expected result                                                   |
|-----------------------------------------|------------------------|-------------------------------------------------------------------|
| Audience submits a valid question       | audience connected     | Receives `question_received` with correct `text`, `slide_index`   |
| Question tagged with current slide      | presenter on slide 2   | `question.slide_index == 2`                                       |
| Presenter notified of new question      | presenter connected    | Presenter receives `question_received` after audience submits     |
| Presenter not in room — no crash        | no presenter connected | No error; question still stored; submitter still gets confirmation|
| Presenter sends `question_submit`       | presenter connected    | Receives `error("unauthorized")`                                  |
| Audience sends `get_questions`          | audience connected     | Receives `error("unauthorized")`                                  |
| Presenter requests `get_questions`      | 2 questions in room    | Receives `questions_list` with both questions in order            |
| Presenter connects with existing questions | 3 questions exist   | Receives `questions_list` as part of connect sequence             |
| `get_questions` on empty room           | no questions asked     | Receives `questions_list` with `questions: []`                    |

#### Content validation tests

| Test                                    | Input                          | Expected server response                          |
|-----------------------------------------|--------------------------------|---------------------------------------------------|
| Empty text after trim                   | `text: "   "`                  | `error("invalid_message", "...empty...")`         |
| Text exactly 280 chars                  | `text: "a" * 280`              | `question_received` (accepted)                    |
| Text 281 chars                          | `text: "a" * 281`              | `error("invalid_message", "...280...")`           |
| Missing `text` field                    | `{type: "question_submit"}`    | `error("invalid_message", ...)`                   |
| Leading/trailing whitespace stripped    | `text: "  hello  "`            | stored `text == "hello"`                          |

#### Rate limit tests

| Test                          | Precondition                        | Expected                            |
|-------------------------------|-------------------------------------|-------------------------------------|
| 4th submit within 60s rejected| 3 valid submits already made        | `error("rate_limited", ...)`        |
| Submits reset after window    | 3 submits then 60s pass             | 4th submit accepted                 |

### Frontend

**Unit tests** for `useQuestions` hook using a mock `send` function:

| Scenario                                      | Expected state transition                          |
|-----------------------------------------------|----------------------------------------------------|
| `submitQuestion("")`                          | `lastSubmitError` set; `send` not called           |
| `submitQuestion("a".repeat(281))`             | `lastSubmitError` set; `send` not called           |
| `submitQuestion("valid text")`                | `isSubmitting = true`; `send` called with correct payload |
| `handleMessage(question_received)` while submitting | `isSubmitting = false`; question appended   |
| `handleMessage(questions_list)`               | `questions` replaced with payload list             |
| `handleMessage(error rate_limited)`           | `isSubmitting = false`; `lastSubmitError` set      |
| 10s timeout fires with `isSubmitting` still true | `isSubmitting = false`; `lastSubmitError` set  |
| `clearSubmitError()` after error              | `lastSubmitError = null`                           |

**Component tests** for `AudienceView` question form:

- Submit button disabled when input empty.
- Submit button disabled when `!isConnected`.
- Character count updates as user types.
- Confirmation shown after successful submission (mocked hook).
- Error shown after rate-limited response (mocked hook).

---

## Out of Scope (v1)

The following capabilities are **explicitly excluded** from this specification.
They may be addressed in future versions.

- **Question upvoting / liking** — No audience interaction with other questions.
- **Question moderation / approval queue** — All valid questions are immediately
  visible to the presenter. There is no pending state.
- **Question deletion** — Neither the presenter nor audience can remove questions
  once submitted.
- **Answered / unanswered status** — Questions have no lifecycle beyond
  "submitted". The presenter tracks their progress manually.
- **Database persistence** — Questions are in-memory only and lost when the room
  is destroyed. The SQLite spec (noted in `tech_stack.md`) will address this.
- **Broadcasting questions to the audience** — Audience members cannot see other
  members' questions. Only the presenter sees the full list.
- **Anonymous IDs / de-duplication** — Multiple identical questions from the
  same or different submitters are stored separately.
- **Rich text or markdown in questions** — Plain text only.
- **Question character limit configurability** — 280 is fixed in v1.
