# WebSocket Infrastructure — Feature Specification

## Overview

The WebSocket infrastructure is the real-time communication layer that enables
audience interaction during presentations. It connects the presenter's
full-screen slide view with audience members' companion pages, enabling emoji
reactions, polls, Q&A, and future interactive features.

This spec covers the **transport layer only** — the shared WebSocket plumbing
that all interactive features build on. Individual feature specs (reactions,
polls, Q&A) will define their own message types and UI, but they all flow
through the infrastructure described here.

---

## Architecture

```
┌──────────────────┐         WebSocket          ┌─────────────────┐
│  Presenter View  │◄──────────────────────────►│  FastAPI Server  │
│  (SlideViewer)   │    /ws/{presentation_id}    │  (ConnectionMgr) │
└──────────────────┘         ▲                   └────────┬────────┘
                             │                            │
                    ┌────────┴────────┐                   │
                    │  Audience Page  │◄──────────────────┘
                    │  (Companion)    │    /ws/{presentation_id}
                    └─────────────────┘
```

All clients connect to the same WebSocket endpoint. The server tracks each
connection's **role** (presenter or audience) and routes messages accordingly.
A single FastAPI process manages all rooms in-memory — no external message
broker is needed at this scale.

---

## Rooms

A **room** is a logical grouping of WebSocket connections tied to one active
presentation session. The room is identified by `presentation_id` (the same
identifier used by the existing REST API, e.g. `demo`).

### Room Lifecycle

1. **Created** when the first client connects to `/ws/{presentation_id}`.
2. **Active** while at least one connection remains open.
3. **Destroyed** when the last connection disconnects (after a grace period).

### Room State

| Field                | Type            | Description                                  |
|----------------------|-----------------|----------------------------------------------|
| `presentation_id`    | string          | Room identifier, matches REST API id         |
| `current_slide`      | int             | Zero-based index of the active slide         |
| `presenter`          | connection      | The single presenter connection (or `None`)  |
| `audience`           | set[connection] | All connected audience members               |
| `created_at`         | datetime        | When the room was first created              |

### Grace Period

When the last connection disconnects, the room lingers for **30 seconds**
before being destroyed. This handles brief network interruptions without
losing room state. The grace period is configurable via the environment
variable `WS_ROOM_GRACE_PERIOD_SECONDS` (default: `30`).

---

## Connection Lifecycle

### Endpoint

```
ws://localhost:8000/ws/{presentation_id}?role={presenter|audience}
```

The `role` query parameter determines the client's role in the room. If omitted,
defaults to `audience`.

### Handshake

1. Client opens a WebSocket to `/ws/{presentation_id}?role=<role>`.
2. Server validates:
   - `presentation_id` corresponds to an existing `.md` file on disk.
   - If `role=presenter` and a presenter is already connected to this room,
     the new connection is **rejected** (only one presenter per room).
3. On success, the server:
   - Adds the connection to the room (creating the room if needed).
   - Sends a `connected` message to the client with room state.
   - Broadcasts a `peer_count` update to all connections in the room.
4. On failure, the server closes the WebSocket with an appropriate close code.

### Disconnect

1. Server removes the connection from the room.
2. Broadcasts updated `peer_count` to remaining connections.
3. If no connections remain, starts the grace period timer.

### Close Codes

| Code | Meaning                             | When Used                              |
|------|-------------------------------------|----------------------------------------|
| 1000 | Normal closure                     | Client or server intentionally closing |
| 1001 | Going away                         | Server shutting down                   |
| 4001 | Presentation not found             | Invalid `presentation_id`              |
| 4002 | Presenter slot taken               | Room already has a presenter           |
| 4003 | Invalid role                       | `role` is not `presenter` or `audience`|

---

## Message Protocol

All messages are JSON objects with a `type` field that determines the payload
schema. Messages flow in both directions over the same WebSocket connection.

### Envelope

```json
{
  "type": "<message_type>",
  "timestamp": "<ISO 8601 UTC>",
  ...payload fields
}
```

Every message includes `type` and `timestamp`. Additional fields depend on the
message type.

### Server → Client Messages

#### `connected`

Sent once immediately after a successful handshake.

```json
{
  "type": "connected",
  "timestamp": "2026-03-20T12:00:00Z",
  "role": "audience",
  "presentation_id": "demo",
  "current_slide": 2,
  "audience_count": 15
}
```

| Field             | Type   | Description                              |
|-------------------|--------|------------------------------------------|
| `role`            | string | `"presenter"` or `"audience"`            |
| `presentation_id` | string | The room's presentation id              |
| `current_slide`   | int    | Current slide index (0-based)           |
| `audience_count`  | int    | Number of audience connections in room  |

#### `slide_changed`

Broadcast to all audience members when the presenter navigates.

```json
{
  "type": "slide_changed",
  "timestamp": "2026-03-20T12:01:30Z",
  "slide_index": 3
}
```

#### `peer_count`

Broadcast to all connections when someone joins or leaves.

```json
{
  "type": "peer_count",
  "timestamp": "2026-03-20T12:00:05Z",
  "audience_count": 16,
  "presenter_connected": true
}
```

#### `error`

Sent to a single client when their message is malformed or rejected.

```json
{
  "type": "error",
  "timestamp": "2026-03-20T12:00:10Z",
  "code": "invalid_message",
  "detail": "Missing required field: type"
}
```

| Error Code          | Meaning                                    |
|---------------------|--------------------------------------------|
| `invalid_message`   | Message failed JSON parsing or validation  |
| `unauthorized`      | Action not allowed for this role           |
| `rate_limited`      | Client is sending too many messages        |
| `unknown_type`      | Unrecognized message type                  |

### Client → Server Messages

#### `navigate` (presenter only)

Tells the server the presenter moved to a new slide. The server updates room
state and broadcasts `slide_changed` to all audience members.

```json
{
  "type": "navigate",
  "timestamp": "2026-03-20T12:01:30Z",
  "slide_index": 3
}
```

If sent by an audience member, the server responds with an `error`
(`"unauthorized"`).

#### `ping`

Client heartbeat. The server responds with `pong`. Used to keep the connection
alive through proxies and detect stale connections.

```json
{
  "type": "ping",
  "timestamp": "2026-03-20T12:02:00Z"
}
```

#### `pong` (server response)

```json
{
  "type": "pong",
  "timestamp": "2026-03-20T12:02:00Z"
}
```

### Feature Messages (Extension Points)

Interactive features (reactions, polls, Q&A) add their own message types.
These are not defined here but follow the same envelope format:

| Feature   | Client → Server     | Server → Client          |
|-----------|---------------------|--------------------------|
| Reactions | `reaction`          | `reaction_broadcast`     |
| Polls     | `poll_vote`         | `poll_opened`, `poll_results` |
| Q&A       | `question_submit`   | `question_received`      |

The WebSocket infrastructure routes all messages through the same connection.
The server dispatches to the appropriate handler based on `type`.

---

## Presenter vs Audience Roles

### Presenter

- Only **one** presenter per room.
- Can send `navigate` messages to control the active slide.
- Receives all broadcast messages (peer count, reactions, poll results, questions).
- If the presenter disconnects, the room persists — audience members remain
  connected and see the last known slide. A new presenter can reconnect.

### Audience

- **Unlimited** audience members per room (within server capacity).
- Cannot send `navigate` — slide control is presenter-only.
- Can send feature messages (reactions, poll votes, questions).
- Receives `slide_changed` so the companion page stays in sync.

### Role Enforcement

The server checks the sender's role before processing any message. Messages
that require a specific role are rejected with an `error` message if sent by
the wrong role. This is enforced server-side — the client should not rely on
UI-only restrictions.

---

## Reconnection

Clients should implement automatic reconnection with exponential backoff. The
server is stateless per-connection — a reconnecting client is treated as a new
connection.

### Client Reconnection Strategy

```
Attempt 1: wait 1s
Attempt 2: wait 2s
Attempt 3: wait 4s
Attempt 4: wait 8s
Attempt 5+: wait 15s (cap)
```

Add ±20% jitter to each wait time to avoid thundering herd on server recovery.

### Reconnection Behavior

- On reconnect, the client receives a fresh `connected` message with current
  room state (including `current_slide`), so it can resync immediately.
- The client should not buffer unsent messages during disconnection — reactions
  and votes are ephemeral and it is acceptable to lose them.
- The presenter's SlideViewer should display a brief reconnection indicator
  (e.g. a subtle banner) while disconnected.
- Audience companion pages should show a "Reconnecting..." state and resume
  automatically once the connection is restored.

### Maximum Reconnection Attempts

After **10** consecutive failed reconnection attempts, the client should stop
retrying and display a persistent error message with a manual "Reconnect"
button.

---

## Heartbeat

Both client and server use heartbeats to detect stale connections.

### Application-Level Heartbeat

- The client sends a `ping` message every **30 seconds**.
- If no `pong` is received within **10 seconds**, the client considers the
  connection dead and initiates reconnection.
- The server drops any connection that has not sent any message (including
  `ping`) within **60 seconds**.

### WebSocket Protocol Ping/Pong

FastAPI/Starlette handles WebSocket protocol-level ping/pong frames
automatically. The application-level heartbeat described above runs on top of
this as an additional liveness check visible to application code.

---

## Rate Limiting

To prevent abuse, the server enforces per-connection rate limits:

| Message Category | Limit                    | Window |
|------------------|--------------------------|--------|
| `reaction`       | 5 messages               | 3s     |
| `poll_vote`      | 1 message per poll       | —      |
| `question_submit`| 3 messages               | 60s    |
| `navigate`       | 20 messages              | 10s    |
| All other types  | 30 messages              | 10s    |

When a client exceeds the limit, the server responds with an `error`
(`"rate_limited"`) and drops the offending message. The connection is **not**
closed — the client simply needs to slow down.

Rate limit windows use a sliding-window counter per connection. No shared state
between connections is needed.

---

## Backend Implementation

### Module Structure

```
backend/
├── ws/
│   ├── __init__.py
│   ├── connection_manager.py   # Room and connection tracking
│   ├── handlers.py             # Message dispatch and processing
│   ├── models.py               # WebSocket message Pydantic models
│   └── rate_limiter.py         # Per-connection rate limiting
```

### `ConnectionManager`

The central class that manages all rooms and connections.

```python
class ConnectionManager:
    """Manages WebSocket rooms and connections.

    Attributes:
        rooms: Active rooms keyed by presentation_id.
    """

    async def connect(
        self, websocket: WebSocket, presentation_id: str, role: str
    ) -> None: ...

    async def disconnect(self, websocket: WebSocket) -> None: ...

    async def broadcast_to_room(
        self, presentation_id: str, message: dict
    ) -> None: ...

    async def send_to_presenter(
        self, presentation_id: str, message: dict
    ) -> None: ...

    async def send_to_audience(
        self, presentation_id: str, message: dict
    ) -> None: ...
```

- Single instance, created at app startup and shared via FastAPI's dependency
  injection or app state (`app.state.connection_manager`).
- All state is in-memory — no Redis or database needed for v2 scale.

### WebSocket Route

```python
@router.websocket("/ws/{presentation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    presentation_id: str,
    role: str = Query(default="audience"),
) -> None: ...
```

The route handler:
1. Validates the presentation exists.
2. Calls `connection_manager.connect()`.
3. Enters a receive loop, dispatching messages to `handlers.py`.
4. On disconnect (or exception), calls `connection_manager.disconnect()`.

### Message Validation

All incoming messages are validated against Pydantic models before processing.
Invalid messages receive an `error` response. The server never crashes due to
malformed client input.

### Dependencies

No new Python packages are required. FastAPI includes WebSocket support via
Starlette. The only dependency is the existing `fastapi` + `uvicorn` stack.

---

## Frontend Implementation

### `useWebSocket` Hook

A custom React hook that manages the WebSocket connection lifecycle.

```typescript
interface UseWebSocketOptions {
  presentationId: string;
  role: "presenter" | "audience";
  onMessage?: (message: ServerMessage) => void;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  isReconnecting: boolean;
  audienceCount: number;
  currentSlide: number;
  send: (message: ClientMessage) => void;
  reconnect: () => void;
}

function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn;
```

**Responsibilities:**
- Opens and maintains the WebSocket connection.
- Handles reconnection with exponential backoff.
- Sends application-level heartbeats.
- Parses incoming messages and dispatches to the `onMessage` callback.
- Exposes connection state and a `send` function to the component tree.

### Message Types (TypeScript)

```typescript
// Server → Client
type ServerMessage =
  | ConnectedMessage
  | SlideChangedMessage
  | PeerCountMessage
  | ErrorMessage
  | PongMessage;

// Client → Server
type ClientMessage =
  | NavigateMessage
  | PingMessage;

interface ConnectedMessage {
  type: "connected";
  timestamp: string;
  role: "presenter" | "audience";
  presentation_id: string;
  current_slide: number;
  audience_count: number;
}

interface SlideChangedMessage {
  type: "slide_changed";
  timestamp: string;
  slide_index: number;
}

interface PeerCountMessage {
  type: "peer_count";
  timestamp: string;
  audience_count: number;
  presenter_connected: boolean;
}

interface ErrorMessage {
  type: "error";
  timestamp: string;
  code: string;
  detail: string;
}

interface NavigateMessage {
  type: "navigate";
  timestamp: string;
  slide_index: number;
}

interface PingMessage {
  type: "ping";
  timestamp: string;
}

interface PongMessage {
  type: "pong";
  timestamp: string;
}
```

Feature-specific message types (reactions, polls, Q&A) will extend these union
types when those features are implemented.

### Integration with SlideViewer

The existing `SlideViewer` component gains WebSocket awareness:

- **As presenter:** Uses `useWebSocket` with `role: "presenter"`. When the user
  navigates via keyboard, the component sends a `navigate` message in addition
  to updating local state. Displays audience count somewhere unobtrusive.
- **As audience:** A new companion page (separate route) uses `useWebSocket`
  with `role: "audience"`. Listens for `slide_changed` to keep in sync.
  Does not have keyboard navigation — the slide follows the presenter.

### Connection Status UI

| State          | Indicator                                            |
|----------------|------------------------------------------------------|
| Connected      | No indicator (clean UI)                              |
| Reconnecting   | Subtle pulsing dot or banner: "Reconnecting..."      |
| Disconnected   | Persistent banner: "Connection lost" + Reconnect btn |

---

## Configuration

All configuration via environment variables, consistent with the existing
`PRESENTATIONS_DIR` pattern:

| Variable                          | Default  | Description                           |
|-----------------------------------|----------|---------------------------------------|
| `WS_ROOM_GRACE_PERIOD_SECONDS`   | `30`     | Seconds before empty room is destroyed|
| `WS_HEARTBEAT_INTERVAL_SECONDS`  | `30`     | Client ping interval                  |
| `WS_HEARTBEAT_TIMEOUT_SECONDS`   | `10`     | Max wait for pong before reconnect    |
| `WS_IDLE_TIMEOUT_SECONDS`        | `60`     | Server drops silent connections after |
| `WS_MAX_RECONNECT_ATTEMPTS`      | `10`     | Client gives up after N failures      |

---

## Security Considerations

### v2 (This Spec)

- **No authentication.** Any client can connect as presenter or audience. This
  matches v1's open REST API (no auth, CORS `*`).
- **Input validation.** All messages validated via Pydantic. No raw string
  execution or eval.
- **Rate limiting.** Per-connection limits prevent message flooding.
- **Message size.** The server rejects any single WebSocket message larger than
  **64 KB**. This prevents memory abuse from malicious clients.

### Future (v3+)

- Room passwords or presenter tokens to prevent unauthorized slide control.
- Per-room audience caps to protect server resources.
- TLS enforcement (wss://) in production.
- Audit logging of presenter actions.

---

## Testing Strategy

### Backend

- **Unit tests** for `ConnectionManager`: room creation/destruction, role
  enforcement, grace period behavior, message routing.
- **Unit tests** for `rate_limiter`: window tracking, limit enforcement.
- **Integration tests** using FastAPI's `TestClient.websocket_connect()`:
  full handshake, message exchange, disconnect handling, error paths.
- **Edge cases**: two presenters attempting to join, rapid connect/disconnect,
  malformed messages, oversized messages.

### Frontend

- **Unit tests** for `useWebSocket` hook: connection state transitions,
  reconnection logic, heartbeat timing, message parsing.
- **Mock WebSocket** for deterministic testing (no real server needed).

---

## Out of Scope for This Spec

- Emoji reaction message types and UI (separate spec).
- Poll message types and UI (separate spec).
- Q&A message types and UI (separate spec).
- QR code generation for the audience join link (separate spec).
- Database persistence of interactions (requires SQLite spec).
- Horizontal scaling / multi-process WebSocket (single process is sufficient
  for the expected scale of one presenter + a room of audience members).
- Authentication and authorization beyond role query parameter.
