# Emoji Reactions — Feature Specification

## Overview

Emoji Reactions let audience members express real-time sentiment during a
presentation by tapping one of a curated set of emoji buttons on their
companion page. Each reaction is relayed to the presenter's slide view, where
it appears as a large floating emoji that rises from the bottom of the screen
and fades out — the same visual idiom used by Twitch and YouTube Live.

The feature serves the core mission of the project: give audience members
something delightful and interactive to do with their phones while a
presentation is in progress, creating a visible feedback loop that energises
both the audience and the presenter.

### Goals

- Audience can tap an emoji and see it appear on the presenter's screen within
  a few hundred milliseconds.
- Reactions are purely ephemeral — they appear and disappear, leaving no
  persistent state.
- The UI is usable one-handed on a phone screen.
- Rate limiting (already wired) prevents flooding.

### Non-Goals (Out of Scope)

- Database persistence of reactions.
- Per-reaction or per-slide analytics and counts.
- Custom emoji uploads or free-text reactions.
- Audience members seeing other audience members' reactions (reactions are
  only broadcast to the presenter, not back to audience).
- Moderation or reaction suppression controls.

---

## Allowed Emoji Set

A fixed, curated set of 10 emojis is used for v1. The set is defined as a
constant on both the backend (for validation) and the frontend (for rendering
the picker bar). It is intentionally small so the UI fits on a phone without
scrolling.

| Index | Emoji | Name        |
|-------|-------|-------------|
| 0     | 👍    | thumbs-up   |
| 1     | 👏    | clapping    |
| 2     | ❤️    | heart        |
| 3     | 😂    | laughing    |
| 4     | 😮    | surprised   |
| 5     | 🔥    | fire        |
| 6     | 🎉    | party       |
| 7     | 🤔    | thinking    |
| 8     | 💯    | hundred     |
| 9     | 👀    | eyes        |

The list is authoritative on the backend. Any `emoji` value sent by a client
that is not in this list is rejected as invalid input (see Business Rules).
The frontend maintains the same list locally to render the picker; it does not
need to fetch it from the server.

**Configurability:** In a later version, the allowed set may be sourced from a
config file or environment variable. The implementation should isolate the set
in a single named constant (e.g. `ALLOWED_EMOJIS`) so it can be easily
extracted later.

---

## Message Protocol

Reactions use the same WebSocket transport and envelope format defined in
`websocket_infrastructure.md`. All messages carry `type` and `timestamp`
fields as per the standard envelope.

### `reaction` — Audience → Server

An audience member sends this message when they tap an emoji in the reaction
bar.

```json
{
  "type": "reaction",
  "timestamp": "2026-03-20T14:32:11.042Z",
  "emoji": "🔥"
}
```

| Field       | Type   | Required | Constraints                                |
|-------------|--------|----------|--------------------------------------------|
| `type`      | string | yes      | Must be exactly `"reaction"`               |
| `timestamp` | string | yes      | ISO 8601 UTC datetime                      |
| `emoji`     | string | yes      | Must be one of the 10 allowed emoji values |

**Role restriction:** Only audience members may send `reaction`. If a presenter
sends this message, the server responds with an `error` (`"unauthorized"`) and
drops the message.

**Rate limit:** The `reaction` category is already configured in `rate_limiter.py`
at **5 messages per 3-second window** per connection. Messages exceeding this
limit receive an `error` (`"rate_limited"`) and are dropped. No further action
is taken (the connection is not closed).

### `reaction_broadcast` — Server → Presenter

After accepting a valid `reaction` message, the server constructs a
`reaction_broadcast` and sends it **to the presenter only** (not back to
audience members).

```json
{
  "type": "reaction_broadcast",
  "timestamp": "2026-03-20T14:32:11.105Z",
  "emoji": "🔥"
}
```

| Field       | Type   | Description                                         |
|-------------|--------|-----------------------------------------------------|
| `type`      | string | Always `"reaction_broadcast"`                       |
| `timestamp` | string | Server-generated ISO 8601 UTC datetime              |
| `emoji`     | string | The emoji character, copied verbatim from `reaction`|

**Why presenter only?** The presenter's screen is the shared physical display
visible to the whole room. Broadcasting back to each audience member's phone
would create a confusing multi-screen animation with no benefit and significant
noise. The presenter view is the single visual focal point.

**If no presenter is connected:** The message is silently dropped. The audience
member has still consumed a rate-limit slot (so spamming during a presenterless
room cannot game the limiter once a presenter joins), but no error is returned
to the sender — from the audience's perspective the reaction was sent
successfully.

### Error Responses

The server sends an `error` message (as defined in the infrastructure spec) for
the following reaction-specific scenarios:

| Scenario                              | `code`            | `detail` (example)                          |
|---------------------------------------|-------------------|---------------------------------------------|
| Sender is the presenter               | `"unauthorized"`  | `"Only audience members can send reactions"`|
| `emoji` field missing                 | `"invalid_message"`| `"Missing required field: emoji"`          |
| `emoji` value not in allowed set      | `"invalid_message"`| `"Emoji not in allowed set"`               |
| Rate limit exceeded                   | `"rate_limited"`  | `"Too many messages, slow down"`            |

---

## Backend Implementation

### New Pydantic Models — `backend/ws/models.py`

Add two new models following the existing pattern in `models.py`.

**`ReactionMessage`** (client → server, validated from input):

```python
ALLOWED_EMOJIS: frozenset[str] = frozenset({
    "👍", "👏", "❤️", "😂", "😮", "🔥", "🎉", "🤔", "💯", "👀",
})

class ReactionMessage(BaseModel):
    """Audience member sends an emoji reaction.

    Attributes:
        type: Always ``"reaction"``.
        timestamp: ISO 8601 UTC timestamp.
        emoji: One of the allowed emoji characters.
    """

    type: str = Field("reaction", pattern="^reaction$")
    timestamp: str = Field(default_factory=_utc_now)
    emoji: str

    @field_validator("emoji")
    @classmethod
    def emoji_must_be_allowed(cls, v: str) -> str:
        if v not in ALLOWED_EMOJIS:
            raise ValueError("Emoji not in allowed set")
        return v
```

**`ReactionBroadcastPayload`** (server → client, constructed by server):

```python
class ReactionBroadcastPayload(BaseModel):
    """Server broadcasts an emoji reaction to the presenter.

    Attributes:
        type: Always ``"reaction_broadcast"``.
        timestamp: ISO 8601 UTC timestamp.
        emoji: The emoji character to display.
    """

    type: str = "reaction_broadcast"
    timestamp: str = Field(default_factory=_utc_now)
    emoji: str
```

### Updated Dispatch — `backend/ws/handlers.py`

Add a `reaction` branch to the `_dispatch` function's `if/elif` chain, **before**
the `else` (unknown type) fallback:

```python
elif msg_type == "reaction":
    if role != "audience":
        error = ErrorPayload(
            code="unauthorized",
            detail="Only audience members can send reactions",
        )
        await websocket.send_json(error.model_dump())
        return

    try:
        rxn = ReactionMessage(**data)
    except ValidationError as exc:
        error = ErrorPayload(
            code="invalid_message",
            detail=str(exc),
        )
        await websocket.send_json(error.model_dump())
        return

    broadcast = ReactionBroadcastPayload(emoji=rxn.emoji)
    await manager.send_to_presenter(presentation_id, broadcast.model_dump())
```

New imports required in `handlers.py`:

```python
from backend.ws.models import (
    ErrorPayload,
    NavigateMessage,
    PongPayload,
    ReactionBroadcastPayload,
    ReactionMessage,
    SlideChangedPayload,
)
```

### No Changes Required

- `rate_limiter.py` — The `reaction` limit (5 / 3s) is already configured.
  No changes needed.
- `connection_manager.py` — `send_to_presenter()` already exists.
  No changes needed.

---

## Frontend Implementation

### New TypeScript Types — `frontend/src/types.ts`

Extend the existing `ServerMessage` and `ClientMessage` union types.

**New interfaces to add:**

```typescript
/** Client → Server: audience member sends an emoji reaction. */
export interface ReactionMessage {
  type: 'reaction';
  timestamp: string;
  emoji: string;
}

/** Server → Client: server relays a reaction to the presenter. */
export interface ReactionBroadcastMessage {
  type: 'reaction_broadcast';
  timestamp: string;
  emoji: string;
}
```

**Update the union types:**

```typescript
export type ServerMessage =
  | ConnectedMessage
  | SlideChangedMessage
  | PeerCountMessage
  | ErrorMessage
  | PongMessage
  | ReactionBroadcastMessage;   // ADD

export type ClientMessage =
  | NavigateMessage
  | PingMessage
  | ReactionMessage;             // ADD
```

**The allowed emoji set** (mirrors the backend constant, used by the picker UI):

```typescript
export const ALLOWED_EMOJIS = [
  '👍', '👏', '❤️', '😂', '😮',
  '🔥', '🎉', '🤔', '💯', '👀',
] as const;

export type AllowedEmoji = typeof ALLOWED_EMOJIS[number];
```

### `useReactions` Hook — `frontend/src/hooks/useReactions.ts`

A new hook that manages the local animation queue on the **presenter side**.
It is separate from `useWebSocket` so the animation state has a clear owner
and can be unit-tested in isolation.

```typescript
interface ReactionParticle {
  id: string;          // Unique per particle (e.g. crypto.randomUUID())
  emoji: string;
  /** Horizontal offset as a percentage (0–100) of the container width.
   *  Randomised at spawn time to spread particles across the screen. */
  xPercent: number;
}

interface UseReactionsReturn {
  particles: ReactionParticle[];
  /** Call this when a reaction_broadcast message arrives. */
  addReaction: (emoji: string) => void;
}

function useReactions(ttlMs?: number): UseReactionsReturn;
```

**Behaviour:**

- `addReaction(emoji)` appends a new `ReactionParticle` to `particles`.
  The `id` is a fresh UUID. `xPercent` is a random float in `[5, 95]` to
  keep particles away from the very edges.
- Each particle is automatically removed from `particles` after `ttlMs`
  milliseconds (default: **3000 ms** — matches the CSS animation duration).
  Removal is done with `setTimeout`; the timeout is cleaned up on unmount.
- `particles` is React state. Components re-render each time a particle is
  added or removed.
- The hook does not know about WebSocket. The caller connects the two
  (see `SlideViewer` integration below).

### Audience View Changes — `frontend/src/components/AudienceView.tsx`

Add a reaction bar fixed to the bottom of the audience companion page.

**New functionality:**

1. Retrieve the `send` function from the existing `useWebSocket` call.
2. Render an `<EmojiReactionBar>` component (described below) at the bottom of
   the view.
3. The bar is only visible when `isConnected` is `true`. While disconnected or
   reconnecting, the bar is hidden (or disabled) so reactions cannot be sent
   into a broken connection.

**`sendReaction` callback:**

```typescript
const sendReaction = useCallback((emoji: string) => {
  send({
    type: 'reaction',
    timestamp: new Date().toISOString(),
    emoji,
  });
}, [send]);
```

**Structural diff to the return JSX:**

```tsx
<div className="slide-viewer audience-view">
  {/* ... existing banners ... */}
  <div className="slide-content">
    {/* ... existing slide rendering ... */}
  </div>
  <div className="slide-footer">
    {/* ... existing counter ... */}
  </div>

  {/* NEW */}
  {isConnected && (
    <EmojiReactionBar onReact={sendReaction} />
  )}
</div>
```

### `EmojiReactionBar` Component — `frontend/src/components/EmojiReactionBar.tsx`

A purely presentational component. It renders the 10 emoji buttons and calls a
callback when one is tapped. It has no internal state and no WebSocket
awareness.

```typescript
interface EmojiReactionBarProps {
  onReact: (emoji: string) => void;
}

export default function EmojiReactionBar({ onReact }: EmojiReactionBarProps);
```

**Rendering:**

- A single `<div className="reaction-bar">` containing one `<button>` per
  allowed emoji.
- Each button has `className="reaction-btn"`, an `aria-label` of the emoji's
  name (e.g. `"Send 🔥 reaction"`), and calls `onReact(emoji)` on click.
- The emoji character is rendered as the button's visible text content.
- No internal cooldown or debounce — rate limiting is enforced server-side.
  The button never shows a disabled or "cooling down" state (this keeps the UI
  simple; the server simply drops excess messages silently from the audience's
  perspective).

### Presenter View Changes — `frontend/src/components/SlideViewer.tsx`

Add a reaction overlay that renders floating emoji particles.

**New functionality:**

1. Instantiate `useReactions`.
2. Pass an `onMessage` callback to `useWebSocket` that calls `addReaction`
   when a `reaction_broadcast` arrives.
3. Render a `<ReactionOverlay particles={particles}>` component over the slide.

**Connecting `useWebSocket` to `useReactions`:**

```typescript
const { particles, addReaction } = useReactions();

const handleMessage = useCallback((message: ServerMessage) => {
  if (message.type === 'reaction_broadcast') {
    addReaction(message.emoji);
  }
}, [addReaction]);

const { isConnected, isReconnecting, audienceCount, send, reconnect } = useWebSocket({
  presentationId: id ?? '',
  role: 'presenter',
  onMessage: handleMessage,
});
```

**Overlay in JSX:**

```tsx
<div className="slide-viewer">
  {/* ... existing slide content ... */}
  <div className="slide-footer">
    {/* ... existing footer ... */}
  </div>

  {/* NEW — sits above slide content, pointer-events: none */}
  <ReactionOverlay particles={particles} />
</div>
```

### `ReactionOverlay` Component — `frontend/src/components/ReactionOverlay.tsx`

Renders the floating emoji particles on the presenter screen.

```typescript
interface ReactionParticle {
  id: string;
  emoji: string;
  xPercent: number;
}

interface ReactionOverlayProps {
  particles: ReactionParticle[];
}

export default function ReactionOverlay({ particles }: ReactionOverlayProps);
```

**Rendering:**

- A single `<div className="reaction-overlay">` that fills the viewport
  (absolute position, full width/height, `pointer-events: none`).
- For each particle, render:
  ```tsx
  <span
    key={particle.id}
    className="reaction-particle"
    style={{ left: `${particle.xPercent}%` }}
    aria-hidden="true"
  >
    {particle.emoji}
  </span>
  ```
- The `left` inline style positions each particle horizontally. The vertical
  rise and fade-out are driven entirely by CSS animation (no JS `requestAnimationFrame`).

---

## Visual Design

### CSS — additions to `frontend/src/index.css`

All new classes follow the existing naming conventions in the stylesheet.

#### Reaction Bar (Audience Side)

```css
/* ─── Emoji reaction bar ────────────────────────────────────────────────── */
.reaction-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem 1rem;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.6) 0%, transparent 100%);
  z-index: 50;
}

.reaction-btn {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 50%;
  width: 3rem;
  height: 3rem;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.1s ease, transform 0.1s ease;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
}

.reaction-btn:hover,
.reaction-btn:focus-visible {
  background: rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.3);
  outline: none;
}

.reaction-btn:active {
  transform: scale(0.88);
}

.reaction-btn:focus-visible {
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.25);
}
```

**Design notes:**
- The gradient scrim ensures the emoji buttons are legible over any slide
  background colour.
- The circular buttons are at least 3rem × 3rem (48px) — above the 44px
  minimum touch target recommended for mobile.
- `touch-action: manipulation` suppresses the 300ms tap delay on mobile browsers.

#### Reaction Overlay (Presenter Side)

```css
/* ─── Reaction overlay (presenter) ─────────────────────────────────────── */
.reaction-overlay {
  position: fixed;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 200;
}

.reaction-particle {
  position: absolute;
  bottom: 0;
  font-size: 3rem;
  line-height: 1;
  user-select: none;
  /* translateX(-50%) centres the emoji on its left anchor point */
  transform: translateX(-50%);
  animation: reaction-float 3s ease-out forwards;
}

@keyframes reaction-float {
  0% {
    transform: translateX(-50%) translateY(0) scale(0.5);
    opacity: 0;
  }
  15% {
    opacity: 1;
    transform: translateX(-50%) translateY(-5vh) scale(1.1);
  }
  85% {
    opacity: 0.9;
    transform: translateX(-50%) translateY(-65vh) scale(1);
  }
  100% {
    opacity: 0;
    transform: translateX(-50%) translateY(-80vh) scale(0.8);
  }
}
```

**Animation breakdown:**

| Keyframe | Effect                                                |
|----------|-------------------------------------------------------|
| 0%       | Particle spawns at the bottom, small and transparent |
| 15%      | Pops into full size and becomes fully opaque         |
| 85%      | Has risen ~65% of viewport height, still visible     |
| 100%     | Faded out at ~80% height; JS removes the DOM node   |

The `3s` animation duration matches the `ttlMs` default in `useReactions` so
the DOM node is cleaned up immediately after the CSS animation finishes. The
`forwards` fill mode keeps the particle invisible after the animation ends,
preventing a flash of the original position during the brief gap between
animation end and DOM removal.

**Multiple simultaneous particles:** Because each particle has an independent
`left` percentage set via inline style, and the CSS animation runs
independently per element, many particles can float simultaneously without any
JavaScript coordination. The browser composites them on the GPU animation layer.

---

## Rate Limiting

The `reaction` category is already registered in `backend/ws/rate_limiter.py`:

```python
"reaction": _WindowConfig(limit=5, window_seconds=3.0),
```

This means each audience connection can send at most **5 reactions in any
rolling 3-second window**. Beyond this, the server returns a `rate_limited`
error and drops the message. The connection is not closed.

The frontend does **not** implement a client-side rate limiter or button disable.
Dropped reactions are silent from the audience's point of view — they see their
button tap animation but the reaction simply does not reach the presenter.
This is acceptable; the burst limit is generous enough that normal enthusiastic
tapping (≈1–2 taps/second) is always within bounds.

---

## Data Flow Diagram

```
Audience Phone                      Server                   Presenter Screen
──────────────────                  ──────────────────────   ──────────────────
[tap 🔥 button]
     │
     ▼
send {type:"reaction",
      emoji:"🔥"}
     │
     └───────────────────────────► validate emoji
                                   check rate limit
                                   construct broadcast
                                        │
                                        └────────────────► receive
                                                           {type:"reaction_broadcast",
                                                            emoji:"🔥"}
                                                                │
                                                                ▼
                                                           addReaction("🔥")
                                                           spawn particle at
                                                           random x position
                                                                │
                                                                ▼
                                                           CSS animation:
                                                           rise + fade (3s)
                                                                │
                                                                ▼
                                                           setTimeout removes
                                                           particle from state
```

---

## Testing Strategy

### Backend

**Unit tests — `tests/ws/test_reaction_handler.py`**

Test the `_dispatch` function in isolation using a mock `ConnectionManager`
and mock `WebSocket`.

| Test case | Input | Expected outcome |
|-----------|-------|-----------------|
| Valid reaction, audience role, presenter connected | `{type:"reaction", emoji:"🔥"}` | `send_to_presenter` called with `reaction_broadcast` payload containing `emoji:"🔥"` |
| Valid reaction, no presenter connected | same as above, but `send_to_presenter` is a no-op | No error returned to sender; silently dropped |
| Sender is presenter role | `{type:"reaction", emoji:"🔥"}` from presenter | `send_json` called with `error` code `unauthorized` |
| Missing `emoji` field | `{type:"reaction"}` | `send_json` called with `error` code `invalid_message` |
| Unknown emoji value | `{type:"reaction", emoji:"💩"}` | `send_json` called with `error` code `invalid_message` |
| All 10 allowed emojis | One test per emoji | Each dispatches `reaction_broadcast` without error |

**Unit tests — `tests/ws/test_models.py`** (extend existing file)

| Test case | Assertion |
|-----------|-----------|
| `ReactionMessage` with valid emoji | Constructs without error |
| `ReactionMessage` with invalid emoji string | Raises `ValidationError` |
| `ReactionMessage` missing `emoji` | Raises `ValidationError` |
| `ReactionBroadcastPayload` | Serialises to expected JSON shape |

**Integration tests — `tests/ws/test_websocket_integration.py`** (extend existing)

Using FastAPI's `TestClient` with `websocket_connect()`:

| Test case | Steps | Assertion |
|-----------|-------|-----------|
| Full reaction round-trip | Connect audience + presenter; audience sends `reaction`; await presenter message | Presenter receives `reaction_broadcast` with correct emoji |
| Reaction from presenter rejected | Connect as presenter; send `reaction` | Presenter receives `error` `unauthorized` |
| Rate limit enforcement | Connect as audience; send 6 reactions in rapid succession | 5th succeeds; 6th returns `rate_limited` error |
| Invalid emoji rejected | Connect as audience; send `reaction` with `emoji:"not-an-emoji"` | Receives `error` `invalid_message` |
| No presenter — reaction silently dropped | Connect as audience only; send `reaction` | No error; no crash |

### Frontend

**`useReactions` hook — unit tests**

Use a testing library that supports hook testing with fake timers.

| Test case | Assertion |
|-----------|-----------|
| `addReaction("🔥")` | `particles` gains one entry with the correct emoji |
| `xPercent` is in `[5, 95]` | Property assertion on spawned particle |
| Particle removed after `ttlMs` | After advancing fake timer by ttlMs, `particles` is empty |
| Multiple reactions before TTL | Each `addReaction` call adds a distinct particle; all present before TTL |
| Cleanup on unmount | Unmounting the hook does not cause state-update warnings (timers cleared) |

**`EmojiReactionBar` — unit tests**

| Test case | Assertion |
|-----------|-----------|
| Renders 10 buttons | 10 `<button>` elements present in the DOM |
| Clicking a button calls `onReact` | Mock callback called with the correct emoji string |
| All 10 emojis rendered | Each emoji character present in the rendered output |
| Accessible labels | Each button has `aria-label` containing the word "reaction" |

**`ReactionOverlay` — unit tests**

| Test case | Assertion |
|-----------|-----------|
| Empty `particles` prop | Overlay renders with no children |
| Particles rendered with correct emoji | Each particle's text content matches its `emoji` |
| `left` style applied correctly | Inline `style.left` matches `xPercent` |
| `aria-hidden` on particles | Each particle span has `aria-hidden="true"` |

**`SlideViewer` / `AudienceView` — integration tests**

Use a mock WebSocket (replace `window.WebSocket` with a test stub) and exercise
the full component render.

| Test case | Component | Assertion |
|-----------|-----------|-----------|
| Incoming `reaction_broadcast` spawns particle | `SlideViewer` | `ReactionOverlay` gets a particle with matching emoji |
| Tapping emoji calls `send` with correct message | `AudienceView` | Mock `send` called with `{type:"reaction", emoji:"🔥"}` |
| Reaction bar hidden when disconnected | `AudienceView` | `EmojiReactionBar` not in DOM when `isConnected` is false |
| Reaction bar visible when connected | `AudienceView` | `EmojiReactionBar` in DOM when `isConnected` is true |

---

## Dependencies

### Depends On

- **WebSocket Infrastructure** (`websocket_infrastructure.md`) — all messages flow
  through the existing WS transport. The `ConnectionManager.send_to_presenter()`
  method is used as-is.
- **Rate Limiter** (`backend/ws/rate_limiter.py`) — the `reaction` limit is
  pre-configured; no changes needed.
- **`useWebSocket` hook** — the `onMessage` callback extension point is used
  to funnel `reaction_broadcast` messages into `useReactions`.

### Depended On By

Nothing currently depends on this feature. Future analytics or moderation
features may consume the reaction message stream.

---

## Open Questions

1. **Should audience members see reactions too?** The current spec routes
   reactions only to the presenter. A future enhancement could also broadcast
   to audience (e.g., so phone screens show a small particle too). This would
   require changing `send_to_presenter` to `broadcast_to_room` or adding a
   new targeted broadcast. Not planned for v1.

2. **Slide-scoped reactions:** Should a `reaction_broadcast` carry the current
   `slide_index` so the presenter view can clear particles on slide change?
   Currently particles naturally expire via TTL, so a slide change mid-flight
   will show particles that were already in progress. This is probably fine but
   warrants a UX decision.

3. **Particle density cap:** With many audience members, the presenter screen
   could become overwhelmed. A `MAX_VISIBLE_PARTICLES` cap (e.g. 30) could be
   enforced in `useReactions` by dropping the oldest particle when the cap is
   reached. Not implemented in v1; the rate limiter (5/3s per connection)
   provides a natural ceiling.
