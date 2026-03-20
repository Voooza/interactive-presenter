# Polls / Multiple Choice Questions — Feature Specification

## Overview

Polls let a presenter embed multiple-choice questions directly in the
Markdown presentation file. When the presenter navigates to a slide that
contains a poll, the poll opens automatically and audience members see a
set of vote buttons on their companion page. As votes arrive the presenter
sees a live bar chart overlaid on their slide. When the presenter navigates
away, the poll closes and no further votes are accepted.

This feature is built entirely on top of the WebSocket infrastructure
described in `websocket_infrastructure.md`. All messages use the same JSON
envelope format and flow through the existing connection. No new transport
layer or persistence store is required.

### Key behaviours

- A poll is **attached to exactly one slide**. There is at most one active
  poll per room at any given time.
- Polls open and close automatically on slide navigation — the presenter
  does not need to click anything.
- Each audience member may cast **exactly one vote per poll**. The vote is
  anonymous: the server records which connection IDs voted but never
  exposes that mapping to any client.
- Results are broadcast to **all clients** (presenter and audience) in
  real time after every vote.
- After voting, an audience member sees live-updating results for the
  remainder of the time the poll is open.
- Votes cast before a poll is re-opened (by navigating back to the slide)
  are **not** carried forward — each visit to a poll slide starts a fresh
  vote count.

---

## Poll Definition in Markdown

Polls are defined inside a slide's body using an HTML comment fence. This
syntax is invisible when the Markdown is rendered as plain HTML, keeps the
file readable, and does not require a custom Markdown extension.

### Syntax

```
<!-- poll -->
- <option text>
- <option text>
- <option text>
<!-- /poll -->
```

Rules:

- The opening tag is the exact string `<!-- poll -->` on its own line
  (leading/trailing whitespace ignored).
- The closing tag is the exact string `<!-- /poll -->` on its own line
  (leading/trailing whitespace ignored).
- Everything between the two tags is the list of options. Each non-blank
  line that starts with `- ` (hyphen then space) is an option. The option
  text is the remainder of the line after `- `, stripped of leading and
  trailing whitespace.
- Non-list lines between the tags (e.g. blank lines or prose) are ignored.
- A slide may contain **at most one** poll block. If more than one block
  is present only the first is used; the rest are silently ignored.
- A poll must have **between 2 and 6 options** inclusive. Fewer than 2
  options is a parser error (the poll is discarded). More than 6 options
  is a parser error (the poll is discarded). Both cases should emit a
  warning to the server log.

### Example

```markdown
# What is your favorite programming language?

Vote now — we'll share the results on the next slide.

<!-- poll -->
- Python
- JavaScript
- Rust
- Go
<!-- /poll -->
```

The slide title ("What is your favorite programming language?") is
**separate** from the poll. It appears in the normal slide heading. The
body text above the poll block renders as usual. The `<!-- poll -->`
comment block is **not** rendered to the audience's slide body — the
parser strips it before returning the slide content string.

### Poll identifier

Each poll is identified by the **zero-based slide index** of the slide it
belongs to. This is stable for the lifetime of a presentation file (slides
are never reordered at runtime). The `poll_id` field in all messages equals
the string `"<presentation_id>:<slide_index>"`, e.g. `"demo:3"`.

---

## Entities

### `PollDefinition`

Extracted from the Markdown file at parse time. Immutable for the lifetime
of the server process.

| Field         | Type           | Description                                              |
|---------------|----------------|----------------------------------------------------------|
| `slide_index` | int            | Zero-based index of the slide that owns this poll        |
| `options`     | list[string]   | Ordered list of option texts (2–6 items)                 |

### `PollState`

Runtime state held per room in memory. Created when a poll opens; replaced
(not mutated) when the same poll is re-visited.

| Field          | Type                  | Description                                              |
|----------------|------------------------|----------------------------------------------------------|
| `poll_id`      | string                | `"<presentation_id>:<slide_index>"`                      |
| `slide_index`  | int                   | Which slide this poll belongs to                         |
| `options`      | list[string]          | Same ordered list as `PollDefinition`                    |
| `votes`        | list[int]             | Vote count per option, parallel to `options`             |
| `voted_ids`    | set[connection_id]    | Opaque IDs of connections that have voted                |
| `is_open`      | bool                  | `true` while accepting votes                             |

`connection_id` is an opaque server-internal identifier, never sent to any
client.

### Constraints

- `len(votes) == len(options)` always.
- All entries in `votes` are non-negative integers.
- `voted_ids` is never exposed outside the server.

---

## Message Protocol

All messages follow the standard envelope from the WebSocket infrastructure
spec:

```json
{
  "type": "<message_type>",
  "timestamp": "<ISO 8601 UTC>",
  ...payload fields
}
```

### Server → Client

#### `poll_opened`

Broadcast to **all** connections in the room when a poll-bearing slide
becomes the active slide (i.e. when `navigate` sets `current_slide` to a
slide that has a poll definition).

This message replaces the name `poll_start` used in the infrastructure
spec's extension-point table — `poll_opened` is more descriptive and
consistent with `poll_closed`.

```json
{
  "type": "poll_opened",
  "timestamp": "2026-03-20T12:05:00Z",
  "poll_id": "demo:3",
  "slide_index": 3,
  "options": ["Python", "JavaScript", "Rust", "Go"],
  "votes": [0, 0, 0, 0]
}
```

| Field         | Type         | Description                                               |
|---------------|--------------|-----------------------------------------------------------|
| `poll_id`     | string       | Stable identifier for this poll instance                  |
| `slide_index` | int          | Slide that owns the poll (0-based)                        |
| `options`     | list[string] | Ordered option labels                                     |
| `votes`       | list[int]    | Current vote counts (all zeros on fresh open)             |

On reconnect, a newly connected audience member receives the current
`PollState` (if a poll is open) via the `connected` message extension
described below, **not** a replayed `poll_opened`. This means clients must
handle poll state that arrives embedded in `connected` as well as through
`poll_opened`.

#### `poll_results`

Broadcast to **all** connections after every successful vote. Contains the
full current vote tally.

```json
{
  "type": "poll_results",
  "timestamp": "2026-03-20T12:05:12Z",
  "poll_id": "demo:3",
  "slide_index": 3,
  "options": ["Python", "JavaScript", "Rust", "Go"],
  "votes": [4, 2, 7, 1],
  "total_votes": 14
}
```

| Field         | Type         | Description                                               |
|---------------|--------------|-----------------------------------------------------------|
| `poll_id`     | string       | Identifies which poll these results belong to             |
| `slide_index` | int          | Slide that owns the poll                                  |
| `options`     | list[string] | Ordered option labels (same order as `poll_opened`)       |
| `votes`       | list[int]    | Current vote count per option                             |
| `total_votes` | int          | Sum of all votes (convenience field)                      |

#### `poll_closed`

Broadcast to **all** connections when the presenter navigates away from a
poll slide (i.e. when `current_slide` changes from a poll-bearing slide to
any other slide). Carries the final tally.

```json
{
  "type": "poll_closed",
  "timestamp": "2026-03-20T12:06:00Z",
  "poll_id": "demo:3",
  "slide_index": 3,
  "options": ["Python", "JavaScript", "Rust", "Go"],
  "votes": [12, 5, 18, 3],
  "total_votes": 38
}
```

Fields are identical to `poll_results`. After receiving `poll_closed`,
clients must not allow further voting and should render the results in a
"closed" (read-only) state.

### Client → Server

#### `poll_vote`

Sent by an **audience member** to cast a vote. Presenter role is not
allowed to vote (see role enforcement below).

```json
{
  "type": "poll_vote",
  "timestamp": "2026-03-20T12:05:08Z",
  "poll_id": "demo:3",
  "option_index": 2
}
```

| Field          | Type   | Constraints                                              |
|----------------|--------|----------------------------------------------------------|
| `poll_id`      | string | Must match the currently open poll in the room           |
| `option_index` | int    | 0-based index into the poll's `options` list             |

**Validation and error responses:**

| Condition                                      | Error code       | Detail                                 |
|------------------------------------------------|------------------|----------------------------------------|
| Sent by presenter role                         | `unauthorized`   | "Only audience members can vote"       |
| No poll is currently open in the room          | `invalid_message`| "No poll is currently open"            |
| `poll_id` does not match the open poll         | `invalid_message`| "Vote is for a different poll"         |
| `option_index` out of range                    | `invalid_message`| "Invalid option index"                 |
| Connection has already voted in this poll      | `rate_limited`   | "You have already voted in this poll"  |

On success, the server:
1. Increments `votes[option_index]` in the `PollState`.
2. Adds the connection's opaque ID to `voted_ids`.
3. Broadcasts a `poll_results` message to all connections in the room.
4. Sends no individual acknowledgement — the broadcast `poll_results` serves as confirmation.

### `connected` message extension

The existing `connected` message (sent on handshake) is extended with an
optional `active_poll` field. If a poll is currently open when a client
connects, this field is populated; otherwise it is omitted or `null`.

```json
{
  "type": "connected",
  "timestamp": "2026-03-20T12:05:30Z",
  "role": "audience",
  "presentation_id": "demo",
  "current_slide": 3,
  "audience_count": 22,
  "active_poll": {
    "poll_id": "demo:3",
    "slide_index": 3,
    "options": ["Python", "JavaScript", "Rust", "Go"],
    "votes": [4, 2, 7, 1],
    "total_votes": 14,
    "has_voted": false
  }
}
```

The `has_voted` field is `true` if the reconnecting connection's ID is
already in `voted_ids`. Because connection IDs change on reconnect, a
reconnecting audience member who already voted will receive `has_voted:
false` and be allowed to vote again. This is an acceptable trade-off to
avoid linking vote history to client identity across sessions.

---

## Poll Lifecycle

```
Presenter navigates TO a poll slide
          │
          ▼
  Server opens PollState (votes all zero, is_open = true)
  Server broadcasts poll_opened to all clients
          │
          ▼
  Audience members send poll_vote
  Server validates, tallies, broadcasts poll_results after each vote
          │
          ▼
Presenter navigates AWAY from the poll slide
          │
          ▼
  Server sets PollState.is_open = false
  Server broadcasts poll_closed (final tally) to all clients
  Server discards PollState
```

**Re-visiting a poll slide:** If the presenter navigates back to a poll
slide that was previously closed, a brand-new `PollState` is created with
zero votes. The old results are discarded (not persisted). A fresh
`poll_opened` is broadcast with empty tallies. All audience members may
vote again.

**Navigating between non-poll slides:** No poll messages are sent.

**Presenter disconnects while poll is open:** The poll remains open (the
room persists, as per the WebSocket infrastructure spec). Audience members
can still vote. When a new presenter reconnects to the same room, the poll
is still open and the presenter receives the current `active_poll` state
via `connected`. The poll only closes on explicit navigation.

---

## Rate Limiting

The `poll_vote` message type is already registered in the rate limiter with
a limit of **1 message per poll**. This is implemented as a special-case
rule: after a `poll_vote` message is accepted, the rate limiter for that
connection and that message type is saturated until the poll closes (at
which point the counter is reset). The server-side duplicate-vote check in
`voted_ids` provides a second, independent guard.

No changes to `rate_limiter.py` are required. The existing configuration
covers this message type.

---

## Backend Implementation

### Parser changes (`backend/parser.py`)

The parser must be extended to detect and extract poll blocks from slide
bodies.

**New data structure:**

```
PollDefinition:
  slide_index: int
  options: list[string]
```

This is a plain data class, not a Pydantic model (it is build-time data,
not API-facing). It should live in `backend/parser.py` alongside the
parsing logic.

**New return value:**

`parse_markdown` currently returns `list[Slide]`. Change the return type
to a named tuple or dataclass:

```
ParseResult:
  slides: list[Slide]
  polls: dict[int, PollDefinition]   # keyed by slide_index
```

Alternatively, add an optional `poll` field to the existing `Slide` model:

```
Slide:
  index: int
  title: str
  content: str
  poll: PollDefinition | None = None
```

The second approach (poll on Slide) is preferred because it keeps poll
metadata co-located with the slide it belongs to. The REST API `GET
/presentations/{id}/slides` endpoint must include `poll` in the response
so the frontend knows which slides have polls.

**Parsing algorithm addition:**

After collecting body lines for a slide (and before calling `_flush`), scan
the body for a poll block:

1. Find the first line that matches `<!-- poll -->` (stripped).
2. Find the next line that matches `<!-- /poll -->` (stripped).
3. Extract lines between them; collect those matching `^- ` as options
   (strip the `- ` prefix and whitespace).
4. Validate option count: 2–6. If invalid, log a warning and treat the
   slide as having no poll.
5. Remove all lines from `<!-- poll -->` through `<!-- /poll -->` (inclusive)
   from the body before building the `content` string. This ensures the raw
   comment syntax is never sent to the frontend.
6. Attach the `PollDefinition` to the `Slide`.

The poll block may appear anywhere in the slide body (before, after, or
between other content). Only the first block in each slide is used.

**Example — parser input/output:**

Input body lines for slide at index 3:
```
Vote now — we'll share the results on the next slide.

<!-- poll -->
- Python
- JavaScript
- Rust
- Go
<!-- /poll -->
```

Output `Slide`:
```
Slide(
  index=3,
  title="What is your favorite programming language?",
  content="Vote now — we'll share the results on the next slide.",
  poll=PollDefinition(
    slide_index=3,
    options=["Python", "JavaScript", "Rust", "Go"]
  )
)
```

### Poll state in `ConnectionManager` (`backend/ws/connection_manager.py`)

Add an `active_poll` field to `_Room`:

```
_Room:
  ...existing fields...
  active_poll: PollState | None = None
```

`PollState` is a dataclass defined in a new module `backend/ws/poll_manager.py`
(or inline in `connection_manager.py`):

```
@dataclass
class PollState:
  poll_id: str
  slide_index: int
  options: list[str]
  votes: list[int]          # len == len(options)
  voted_ids: set[int]       # internal connection object ids, never sent to clients
  is_open: bool = True
```

No new public methods on `ConnectionManager` are required for poll state
management — the handler logic directly reads and mutates `room.active_poll`.

### New `poll_manager.py` module (`backend/ws/poll_manager.py`)

Isolate poll business logic in a dedicated module to keep `handlers.py`
readable.

```
def open_poll(room, poll_def: PollDefinition) -> PollState:
    """Create a fresh PollState on the room and return it."""

def close_poll(room) -> PollState | None:
    """Mark the poll as closed, remove it from the room, return final state."""

def record_vote(
    poll: PollState,
    option_index: int,
    connection_id: int,
) -> None:
    """Increment vote count and record the connection id. Raises on duplicate."""
```

`connection_id` is `id(connection_object)` — the Python object id of the
`_Connection` instance. This is stable for the lifetime of the connection
and never shared with clients.

### Handler changes (`backend/ws/handlers.py`)

#### `navigate` handler — poll open/close logic

After updating `room.current_slide`, the navigate handler must:

1. **Close any currently open poll** if `room.active_poll` is set and the
   new slide index differs from `active_poll.slide_index`:
   - Call `close_poll(room)` to get the final state.
   - Broadcast `poll_closed` to all connections.

2. **Open a new poll** if the new slide has a `PollDefinition`:
   - Look up the slide's poll definition from the loaded presentation data
     (the handler must have access to the parsed slide list — see below).
   - Call `open_poll(room, poll_def)` to create fresh state.
   - Broadcast `poll_opened` to all connections.

The handler needs access to the presentation's parsed slides to look up poll
definitions. The recommended approach is to cache parsed presentations in
`app.state.presentations` at startup (or on first access) as a dict keyed
by `presentation_id`. This is a pre-existing need (the REST API already
parses on request) — polls are the motivation for caching.

#### New `poll_vote` handler branch

Add a branch to `_dispatch` for `msg_type == "poll_vote"`:

```
if msg_type == "poll_vote":
    await _handle_poll_vote(manager, websocket, conn, presentation_id, data)
```

`_handle_poll_vote`:
1. Reject if `conn.role == "presenter"` → `error("unauthorized", ...)`.
2. Parse and validate `PollVoteMessage` via Pydantic → `error("invalid_message", ...)` on failure.
3. Look up `room.active_poll`. If `None` → `error("invalid_message", "No poll is currently open")`.
4. Check `msg.poll_id == room.active_poll.poll_id`. If not → `error("invalid_message", "Vote is for a different poll")`.
5. Check `msg.option_index` in range. If not → `error("invalid_message", "Invalid option index")`.
6. Check `id(conn) not in room.active_poll.voted_ids`. If already voted → `error("rate_limited", "You have already voted in this poll")`.
7. Call `record_vote(room.active_poll, msg.option_index, id(conn))`.
8. Build and broadcast `PollResultsPayload` to all connections.

#### `connect` handler extension

After sending the `ConnectedPayload`, check `room.active_poll`:

- If set, append `active_poll` to the connected payload (or send a separate
  follow-up `poll_opened` message to the new connection only).

The preferred approach is a **follow-up message**: immediately after the
`connected` message, if a poll is open, send a `poll_opened` message
(with current vote counts) directly to the new connection. This reuses the
existing `poll_opened` payload type and avoids changing the `connected`
message schema.

The `connected` message extension with `active_poll` described in the
protocol section above is an alternative; the implementation team may choose
either. Both must produce the same end state in the client.

### New Pydantic models (`backend/ws/models.py`)

Add the following models:

```python
# Client → Server
class PollVoteMessage(BaseModel):
    type: str = Field("poll_vote", pattern="^poll_vote$")
    timestamp: str = Field(default_factory=_utc_now)
    poll_id: str
    option_index: int

# Server → Client
class PollOpenedPayload(BaseModel):
    type: str = "poll_opened"
    timestamp: str = Field(default_factory=_utc_now)
    poll_id: str
    slide_index: int
    options: list[str]
    votes: list[int]

class PollResultsPayload(BaseModel):
    type: str = "poll_results"
    timestamp: str = Field(default_factory=_utc_now)
    poll_id: str
    slide_index: int
    options: list[str]
    votes: list[int]
    total_votes: int

class PollClosedPayload(BaseModel):
    type: str = "poll_closed"
    timestamp: str = Field(default_factory=_utc_now)
    poll_id: str
    slide_index: int
    options: list[str]
    votes: list[int]
    total_votes: int
```

---

## Frontend Implementation

### TypeScript types (`frontend/src/types.ts`)

Extend the existing message union types:

```typescript
// New server → client poll messages
export interface PollOpenedMessage {
  type: 'poll_opened';
  timestamp: string;
  poll_id: string;
  slide_index: number;
  options: string[];
  votes: number[];
}

export interface PollResultsMessage {
  type: 'poll_results';
  timestamp: string;
  poll_id: string;
  slide_index: number;
  options: string[];
  votes: number[];
  total_votes: number;
}

export interface PollClosedMessage {
  type: 'poll_closed';
  timestamp: string;
  poll_id: string;
  slide_index: number;
  options: string[];
  votes: number[];
  total_votes: number;
}

// New client → server poll message
export interface PollVoteMessage {
  type: 'poll_vote';
  timestamp: string;
  poll_id: string;
  option_index: number;
}

// Extend the union types:
export type ServerMessage =
  | ConnectedMessage
  | SlideChangedMessage
  | PeerCountMessage
  | ErrorMessage
  | PongMessage
  | PollOpenedMessage       // new
  | PollResultsMessage      // new
  | PollClosedMessage;      // new

export type ClientMessage =
  | NavigateMessage
  | PingMessage
  | PollVoteMessage;        // new
```

Also add a `poll` field to the `Slide` type to match the updated REST API:

```typescript
export interface PollOption {
  // No separate type needed — options are plain strings in the API.
}

export interface SlidePoll {
  slide_index: number;
  options: string[];
}

export interface Slide {
  index: number;
  title: string;
  content: string;
  poll: SlidePoll | null;  // new
}
```

### `usePolls` hook (`frontend/src/hooks/usePolls.ts`)

A dedicated hook that manages all poll state for a single session. It is
consumed by both `SlideViewer` and `AudienceView`.

```typescript
export interface PollOption {
  label: string;
  votes: number;
}

export interface ActivePoll {
  pollId: string;
  slideIndex: number;
  options: PollOption[];   // derived from options[] + votes[]
  totalVotes: number;
  isOpen: boolean;
  hasVoted: boolean;
  votedOptionIndex: number | null;
}

export interface UsePollsOptions {
  send: (message: ClientMessage) => void;
}

export interface UsePollsReturn {
  activePoll: ActivePoll | null;
  handlePollMessage: (message: ServerMessage) => void;
  castVote: (optionIndex: number) => void;
}

export function usePolls(options: UsePollsOptions): UsePollsReturn;
```

**Internal state managed by the hook:**

| State field        | Type                | Description                                              |
|--------------------|---------------------|----------------------------------------------------------|
| `activePoll`       | `ActivePoll | null` | Current poll state, or null when no poll is open         |
| `hasVoted`         | `boolean`           | Whether this client has cast a vote in the active poll   |
| `votedOptionIndex` | `number | null`     | Which option index was voted for                         |

**`handlePollMessage(message)`:**

Routes incoming server messages to state updates:

- `poll_opened`: Set `activePoll` from message fields; reset `hasVoted` to
  `false` and `votedOptionIndex` to `null`.
- `poll_results`: Update `activePoll.options` (votes) and `totalVotes`.
  Preserve `hasVoted` / `votedOptionIndex`.
- `poll_closed`: Update `activePoll.options` and `totalVotes`; set
  `activePoll.isOpen = false`.

**`castVote(optionIndex)`:**

1. Guard: do nothing if `activePoll` is null, `activePoll.isOpen` is false,
   or `hasVoted` is true.
2. Set `hasVoted = true` and `votedOptionIndex = optionIndex` optimistically
   in local state (provides instant UI feedback before the server round-trip).
3. Call `send({ type: "poll_vote", timestamp: ..., poll_id: activePoll.pollId, option_index: optionIndex })`.

**Integration:**

Both `SlideViewer` and `AudienceView` should:
1. Pass their `send` function to `usePolls`.
2. Register `handlePollMessage` with `useWebSocket`'s `onMessage` callback
   (in addition to any other message handling).
3. Pass `activePoll`, `castVote` down to the poll UI components.

### Audience poll UI — `PollCard` component

Displayed on `AudienceView` below the slide content when `activePoll` is
not null.

**Before voting (`hasVoted == false`, `activePoll.isOpen == true`):**

Shows a list of clickable option buttons. Each button displays the option
text. Tapping/clicking a button calls `castVote(index)`.

**After voting (or when `hasVoted == true`):**

Shows a compact bar chart (see visual design below) with the current live
tallies. The voted-for option is visually highlighted. If the poll is still
open the chart updates in real time as `poll_results` messages arrive.

**When poll is closed (`activePoll.isOpen == false`):**

Shows the final bar chart with a "Poll closed" label. All options including
the voted-for one remain visible. No vote buttons.

**Component signature:**

```typescript
interface PollCardProps {
  poll: ActivePoll;
  onVote: (optionIndex: number) => void;
}

function PollCard({ poll, onVote }: PollCardProps): JSX.Element;
```

### Presenter poll overlay — `PollOverlay` component

Displayed on `SlideViewer` as a fixed overlay anchored to the bottom-right
of the viewport (above the slide footer) when `activePoll` is not null.

Shows the bar chart immediately — there are no vote buttons on the presenter
view. The presenter sees live results from the moment the poll opens.

When `activePoll.isOpen == false` (the poll is closed), the overlay shows
the final results and a "Poll closed" label, then fades out after 5 seconds.

**Component signature:**

```typescript
interface PollOverlayProps {
  poll: ActivePoll;
}

function PollOverlay({ poll }: PollOverlayProps): JSX.Element;
```

---

## Visual Design

The design follows the existing dark theme (`background: #1a1a1a`,
`color: #f0f0f0`) established in `index.css`.

### PollCard (audience side)

**Vote buttons (pre-vote state):**

```
┌──────────────────────────────────────────────┐
│  What is your favorite programming language? │  ← slide title (already shown above)
│                                              │
│  ┌─────────────────────────────────────────┐ │
│  │  Python                                 │ │
│  ├─────────────────────────────────────────┤ │
│  │  JavaScript                             │ │
│  ├─────────────────────────────────────────┤ │
│  │  Rust                                   │ │
│  ├─────────────────────────────────────────┤ │
│  │  Go                                     │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

- Container: `background: #252525`, `border: 1px solid #333`,
  `border-radius: 12px`, `padding: 1.25rem`.
- Each button: full width, `background: #1e1e1e`, `border: 1px solid #444`,
  `border-radius: 8px`, `padding: 0.75rem 1rem`, `font-size: 1.1rem`,
  `color: #f0f0f0`, `cursor: pointer`.
- Hover state: `background: #2a2a2a`, `border-color: #666`.
- Active/press state: `background: #333`.

**Bar chart (post-vote / results state):**

```
  Python       ████████████████░░░░  32%  12 votes
  JavaScript   ████░░░░░░░░░░░░░░░░   8%   3 votes  ← if this was voted
  Rust         ███████████████████░  46%  17 votes  ← highlight
  Go           ████░░░░░░░░░░░░░░░░  14%   5 votes
               ─────────────────────────────────
               Total: 37 votes
```

- Container: same card style as above.
- Each row: label on the left (fixed width), bar in the middle, percentage
  and raw count on the right.
- Bar: `height: 20px`, `border-radius: 4px`, `background: #3b82f6` (blue).
- Bar width: proportional to the option's share of total votes (0%–100% of
  the bar track width).
- Voted-for option: bar colour `#10b981` (green), label text bold.
- Leading option (highest votes): no special colour unless it is also the
  voted option.
- Percentage: calculated as `Math.round(votes / totalVotes * 100)` or `0`
  when `totalVotes == 0`.
- When `totalVotes == 0` all bars are shown at 0 width.
- Live updates: bar width and counts animate smoothly using CSS transitions
  (`transition: width 0.3s ease`).

**"Poll closed" label:**

A small badge `Poll closed` in muted text (`color: #888`, `font-size: 0.8rem`)
shown in the top-right of the card when `isOpen == false`.

### PollOverlay (presenter side)

A floating panel, not full-width. Positioned fixed at bottom-right, above
the slide footer. Maximum width `360px`, maximum height `40vh` with
`overflow-y: auto`.

```
┌─────────────────────────────────┐
│  Live Poll  ●  14 votes         │
│  Python       ████████   32%    │
│  JavaScript   ██         8%     │
│  Rust         ████████████ 46%  │
│  Go           ███        14%    │
└─────────────────────────────────┘
```

- Background: `rgba(30, 30, 30, 0.92)`, `backdrop-filter: blur(8px)`.
- Border: `1px solid #333`, `border-radius: 12px`.
- Padding: `1rem`.
- Header row: "Live Poll" label on the left, animated green dot (`●`) to
  indicate open status, vote count on the right.
- Bars: same style as `PollCard`, no voted-for highlighting (the presenter
  did not vote).
- "Poll closed" state: header dot turns grey, "Poll closed" replaces "Live
  Poll". Overlay remains for 5 seconds then fades out (`opacity: 0` over
  0.5s, then removed from DOM).

### CSS class naming

| Class                      | Element                                          |
|----------------------------|--------------------------------------------------|
| `.poll-card`               | PollCard container                               |
| `.poll-card__options`      | Vote buttons wrapper                             |
| `.poll-card__option-btn`   | Individual vote button                           |
| `.poll-card__option-btn--hover` | Hover/focus state                           |
| `.poll-card__results`      | Results (bar chart) wrapper                      |
| `.poll-card__row`          | One option row in the results                    |
| `.poll-card__row--voted`   | Row corresponding to the voted option            |
| `.poll-card__label`        | Option label text                                |
| `.poll-card__bar-track`    | Full-width bar background track                  |
| `.poll-card__bar-fill`     | Coloured fill inside the track                   |
| `.poll-card__bar-fill--voted` | Green fill for the voted option               |
| `.poll-card__count`        | "N votes" text on right                          |
| `.poll-card__pct`          | Percentage text                                  |
| `.poll-card__total`        | "Total: N votes" footer                          |
| `.poll-card__closed-badge` | "Poll closed" badge                              |
| `.poll-overlay`            | PollOverlay outer container                      |
| `.poll-overlay__header`    | Header row with live dot and vote count          |
| `.poll-overlay__live-dot`  | Animated green dot                               |
| `.poll-overlay__live-dot--closed` | Grey dot when closed                     |
| `.poll-overlay--fading`    | Applied when poll closes; triggers fade-out      |

---

## Integration with Slide Navigation

### `AudienceView` changes

1. Add `usePolls` call, pass `send`.
2. Wire `handlePollMessage` into `useWebSocket`'s `onMessage`.
3. Render `<PollCard>` below `.slide-content` when `activePoll !== null`.
4. The poll card is part of the normal document flow (not fixed-position)
   so the page scrolls if both the slide content and poll card exceed the
   viewport height.

### `SlideViewer` changes

1. Add `usePolls` call, pass `send`.
2. Wire `handlePollMessage` into `useWebSocket`'s `onMessage`.
3. Render `<PollOverlay>` inside `.slide-viewer` when `activePoll !== null`.
4. The overlay is fixed-position and does not affect slide layout.

---

## Business Rules and Invariants

1. **One poll at a time.** A room can have at most one open poll. Opening a
   new poll (by navigating to a second poll slide) implicitly closes the
   previous one first. The close message is broadcast before the open message.

2. **One vote per connection per poll.** Enforced server-side via `voted_ids`.
   The rate limiter provides a complementary check. Client-side guards are
   UI-only and must not be relied on for correctness.

3. **Votes are anonymous.** The server never sends a `voted_ids` set or any
   mapping from vote to identity to any client.

4. **Poll options are immutable after parsing.** The option list comes from
   the `.md` file and never changes while the server is running. Clients may
   cache the option list from `poll_opened`.

5. **Navigation is authoritative.** Only the `navigate` message triggers poll
   open/close. Audience members cannot open or close polls.

6. **Poll ID stability within a session.** The `poll_id` format is
   `"<presentation_id>:<slide_index>"`. Within a single server session a
   given poll ID always refers to the same poll definition. If the `.md`
   file changes on disk and the server reloads, poll IDs remain stable as
   long as slide indices do not shift.

7. **Empty vote state on re-open.** Navigating back to a poll slide that was
   previously open and closed creates a fresh `PollState` with zero votes.
   Audience members who voted in the previous open are eligible to vote again.

8. **No partial broadcasts.** `poll_results` is broadcast only after a vote
   is fully recorded. There is no intermediate state visible to clients where
   the count is partially updated.

9. **`option_index` is zero-based** and must be in the range
   `[0, len(options) - 1]` inclusive. The server validates this before
   recording the vote.

10. **Presenter cannot vote.** Sending `poll_vote` from a presenter
    connection always returns `error("unauthorized", ...)` regardless of
    whether a poll is open.

---

## Dependencies

### What polls depend on

- **WebSocket infrastructure** (`websocket_infrastructure.md`): rooms,
  connection management, message dispatch, rate limiter, role enforcement.
  All poll messages flow through the existing infrastructure unchanged.
- **Markdown parser** (`backend/parser.py`): must be extended to extract
  poll definitions. The poll feature depends on this extension.
- **Slide REST API** (`GET /presentations/{id}/slides`): must include `poll`
  data in the response so the frontend knows which slides have polls without
  needing to reparse Markdown.

### What depends on polls

- **Results slide feature** (future): a follow-on feature may display a
  static bar chart of a previous poll on a subsequent slide. That feature
  would depend on persisted poll results, which is out of scope here.
- **Q&A feature** (separate spec): no dependency on polls. Both are
  independent interactive features.

---

## Testing Strategy

### Backend — parser tests

File: `tests/test_parser.py` (extend existing test file or add new one).

| Test case | Description |
|-----------|-------------|
| Slide with poll block | `parse_markdown` returns `Slide` with `poll` set; `content` has poll comment stripped |
| Slide without poll block | `Slide.poll` is `None` |
| Poll block stripped from content | Rendered `content` contains no `<!-- poll -->` text |
| Multiple poll blocks in one slide | Only the first is used; warning logged |
| Fewer than 2 options | `poll` is `None`; warning logged |
| More than 6 options | `poll` is `None`; warning logged |
| Poll block at start of body | Correct options extracted; non-poll content preserved |
| Poll block at end of body | Same |
| Poll block in middle of body | Surrounding content preserved on both sides |
| Options with extra whitespace | Option text is stripped |
| Mixed blank and list lines between tags | Only `- ` lines become options |
| Multi-slide file with one poll | Only the correct slide has `poll` set |
| Fenced code block containing poll syntax | Parser does not extract poll (inside code block) |

### Backend — handler tests

File: `tests/test_ws_handlers.py` (extend existing or new).

| Test case | Description |
|-----------|-------------|
| Navigate to poll slide → `poll_opened` broadcast | All clients receive correct payload |
| Navigate away from poll slide → `poll_closed` broadcast | Final tally in payload |
| Navigate poll→poll → close then open | `poll_closed` before `poll_opened` |
| Navigate non-poll→non-poll | No poll messages sent |
| Audience votes → `poll_results` broadcast | Vote counted; all clients notified |
| Presenter votes → `unauthorized` error | Vote not recorded |
| Duplicate vote → `rate_limited` error | Count unchanged |
| Vote with wrong `poll_id` → `invalid_message` | Count unchanged |
| Vote with out-of-range `option_index` → `invalid_message` | Count unchanged |
| Vote when no poll open → `invalid_message` | No state changed |
| New audience member connects while poll open | Receives `poll_opened` with current counts |
| Audience member reconnects after voting | Can vote again (new connection id) |
| Poll re-opened (navigate back to slide) | Fresh zero counts; old votes discarded |

### Frontend — `usePolls` hook tests

Use a mock `send` function and call `handlePollMessage` directly.

| Test case | Description |
|-----------|-------------|
| `poll_opened` sets `activePoll` | `activePoll` matches message fields |
| `poll_results` updates vote counts | `options[i].votes` updated correctly |
| `poll_closed` sets `isOpen = false` | Final counts preserved |
| `castVote` while open | `send` called with correct payload; `hasVoted` set |
| `castVote` while `hasVoted == true` | `send` not called |
| `castVote` while `activePoll == null` | `send` not called |
| `castVote` while `isOpen == false` | `send` not called |
| Optimistic `hasVoted` on vote | `hasVoted` true immediately, before server round-trip |
| `poll_opened` resets `hasVoted` | Previous vote state cleared on new poll |

### Frontend — `PollCard` component tests

Use a test renderer with mock `ActivePoll` data.

| Test case | Description |
|-----------|-------------|
| Pre-vote state renders buttons | One button per option |
| Clicking a button calls `onVote(index)` | Correct index passed |
| Post-vote state renders bar chart | Buttons replaced with bars |
| Voted option has green bar | `.poll-card__bar-fill--voted` applied |
| Bar widths reflect vote proportions | Verified by checking inline `width` style |
| Closed state shows "Poll closed" badge | Badge element present |
| Zero total votes → zero-width bars | No division-by-zero crash |

---

## Out of Scope

- **Database persistence.** Poll results are in-memory only. Results are lost
  when the server restarts.
- **Multiple simultaneous active polls.** At most one poll is open per room
  at any time.
- **Poll editing after creation.** Poll options are defined in the `.md` file
  and cannot be changed at runtime.
- **Named / non-anonymous voting.** Votes are always anonymous. There is no
  mechanism to reveal who voted for what.
- **Vote retraction.** Once cast, a vote cannot be changed or withdrawn.
- **Results-slide automation.** Displaying a bar chart of results on a
  subsequent slide (as mentioned in the mission statement) is a separate
  feature that depends on persistence and is not covered here.
- **Poll analytics / export.** No CSV or report generation.
- **Presenter-controlled poll open/close.** Open and close are entirely
  driven by slide navigation. There are no separate "Start poll" / "End poll"
  controls.
- **Weighted voting or ranked choice.** Each audience member casts exactly
  one vote for exactly one option.
