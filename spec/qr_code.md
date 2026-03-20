# QR Code for Audience Join — Feature Specification

## Overview

When a presenter opens a presentation, the **first slide** (index 0) displays a
QR code overlay in the presenter view. Audience members point their phones at the
screen, scan the code, and land on the companion page
(`/presentations/{id}/audience`) — ready to interact without typing a URL.

The QR code encodes the full audience URL, constructed entirely in the browser
from the current `window.location` origin. No backend changes are required. The
code is generated client-side using a JavaScript library and rendered as an SVG
or canvas element directly in the DOM.

The overlay is **only visible in the presenter view** (`SlideViewer`) and **only
on slide 0**. It disappears automatically as soon as the presenter advances to
the next slide, and reappears if they navigate back to slide 0. The audience
companion page (`AudienceView`) never shows a QR code.

---

## URL Construction

The audience join URL is assembled entirely on the client side. No new backend
endpoint is needed.

### Algorithm

```
base_url  = window.location.origin        // e.g. "http://192.168.1.42:5173"
join_path = "/presentations/{id}/audience"
join_url  = base_url + join_path          // encoded into the QR code
```

`window.location.origin` is the scheme, hostname, and port of the page the
presenter's browser is currently displaying. This means:

| Scenario | `window.location.origin` example | Resulting join URL |
|---|---|---|
| Local dev (same machine) | `http://localhost:5173` | `http://localhost:5173/presentations/demo/audience` |
| LAN (presenter's IP) | `http://192.168.1.42:5173` | `http://192.168.1.42:5173/presentations/demo/audience` |
| Production (HTTPS) | `https://present.example.com` | `https://present.example.com/presentations/demo/audience` |

### Implication for LAN Use

The most common real-world scenario is a presenter broadcasting their laptop
over a projector while the audience uses their phones on the same Wi-Fi network.
For the QR code to work in this case, the presenter must open the app using their
LAN IP address (e.g. `http://192.168.1.42:5173`) rather than `localhost`. When
they do, `window.location.origin` will contain the LAN IP, and audience phones
can reach that address directly. This is a deployment/usage concern, not a code
concern — the spec intentionally delegates URL construction to `window.location`.

> **Open question:** Should the UI surface a hint like "Share this URL with your
> audience" showing the resolved join URL as plain text? This is listed in the
> visual design section as a required element (the URL appears below the QR code),
> which serves this purpose adequately.

---

## Library Recommendation

Use **`qrcode.react`** (the `QRCodeSVG` or `QRCodeCanvas` export).

**Rationale:**
- Pure client-side, zero server round-trips.
- Outputs standard SVG (preferred) or Canvas — both work in all modern browsers.
- Single prop API: pass the URL string and desired size. No configuration
  ceremony needed.
- Actively maintained, widely used, small bundle footprint (< 30 kB gzipped
  including the QR generation logic).
- The SVG output can be styled via CSS without fighting canvas pixel APIs.

**Recommended import:**
```typescript
import { QRCodeSVG } from 'qrcode.react';
```

**Alternative:** `qr-code-styling` is more capable (logo overlays, custom
dot shapes) but those features are explicitly out of scope. Prefer the simpler
library.

---

## Entities

### `QRCodeOverlay` Component

A self-contained React component responsible for rendering the QR panel. It
owns no state beyond what it receives as props; all logic lives in `SlideViewer`.

| Prop | Type | Required | Description |
|---|---|---|---|
| `url` | `string` | yes | The full audience join URL to encode |
| `size` | `number` | no | Side length of the QR code in pixels (default: `200`) |

The component renders a fixed-position panel anchored to the right side of the
viewport. It has no side effects, no network calls, and no WebSocket interaction.

---

## Display Logic

### Conditions for Showing the Overlay

The overlay is rendered if **all** of the following are true:

1. The component rendering is `SlideViewer` (the presenter view), not
   `AudienceView`.
2. Slides have finished loading successfully (`loading === false`,
   `error === null`, `slides.length > 0`).
3. `currentIndex === 0` (the presenter is on the first slide).

If any condition is false, `QRCodeOverlay` is not mounted at all — it should not
render as hidden or invisible; it simply should not exist in the component tree.

### Slide Navigation Behavior

| Event | QR Code state |
|---|---|
| Presenter opens presentation (lands on slide 0) | Visible |
| Presenter advances to slide 1 (→ or Space) | Hidden |
| Presenter retreats back to slide 0 (←) | Visible again |
| Slides still loading | Hidden |
| Slides failed to load | Hidden |

### AudienceView Exclusion

`AudienceView` must never render `QRCodeOverlay` under any circumstances. There
is no conditional logic needed in `AudienceView` — simply do not import or
reference `QRCodeOverlay` there.

---

## Frontend Implementation

### Changes to `SlideViewer`

`SlideViewer` is the only component that changes. No changes to `App.tsx`,
`AudienceView`, `main.tsx`, or any hook.

**New import:**
```typescript
import { QRCodeOverlay } from './QRCodeOverlay';
```

**URL derivation** (inside the component body, before the render return):
```typescript
const joinUrl = `${window.location.origin}/presentations/${id}/audience`;
```

**Conditional render** (inside the JSX, as a sibling of `.slide-content`):
```tsx
{currentIndex === 0 && (
  <QRCodeOverlay url={joinUrl} />
)}
```

The conditional is placed inside the outer `.slide-viewer` div, after the
`.slide-content` div and before the `.slide-footer` div.

### `QRCodeOverlay` Component

Create a new file: `frontend/src/components/QRCodeOverlay.tsx`

```
frontend/src/components/
├── AudienceView.tsx      (unchanged)
├── PresentationList.tsx  (unchanged)
├── QRCodeOverlay.tsx     ← new file
└── SlideViewer.tsx       (modified)
```

**Responsibilities:**
- Accept the `url` prop.
- Derive the human-readable display string from `url` (the full URL, truncated
  with ellipsis if longer than 60 characters for the label underneath).
- Render a fixed-position panel containing the QR code SVG and the URL label.
- Apply all styling via CSS classes defined in `index.css`.

**Component structure (pseudocode):**
```
<div class="qr-overlay">
  <div class="qr-panel">
    <QRCodeSVG value={url} size={200} />
    <p class="qr-url-label">{url}</p>
  </div>
</div>
```

### No Backend Changes

The backend (`routes.py`, `main.py`, `ws/`) requires zero modifications for this
feature. The audience join URL is derived purely from `window.location.origin` in
the browser.

---

## Visual Design

### Layout

The overlay sits **fixed to the right side** of the viewport, vertically
centered. It does not scroll with page content. It does not intercept pointer
events on the slide content area (use `pointer-events: none` on the outer wrapper,
`pointer-events: auto` on the panel itself so the URL text remains
copy-selectable).

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│   ┌────────────────────────────┐   ┌─────────────┐  │
│   │                            │   │  [QR CODE]  │  │
│   │   Slide Title              │   │             │  │
│   │   - bullet                 │   │  ▓▓▓▓▓▓▓▓  │  │
│   │   - bullet                 │   │  ▓      ▓  │  │
│   │                            │   │  ▓  ▓▓  ▓  │  │
│   │                            │   │  ▓      ▓  │  │
│   │                            │   │  ▓▓▓▓▓▓▓▓  │  │
│   │                            │   │             │  │
│   │                            │   │ http://...  │  │
│   └────────────────────────────┘   └─────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Dimensions and Spacing

| Property | Value |
|---|---|
| QR code size | 200 × 200 px |
| Panel padding | 1.25rem on all sides |
| Panel border-radius | 12px |
| Gap between QR and URL label | 0.75rem |
| Distance from right viewport edge | 2rem |
| Panel max-width | 256px |

### Colors

The app uses a dark theme (`background: #1a1a1a`, text `#f0f0f0`). The QR panel
must be legible against this dark background. Phones scanning QR codes work best
with high contrast between the QR modules and the surrounding background.

| Element | Value | Rationale |
|---|---|---|
| Panel background | `rgba(255, 255, 255, 0.08)` | Subtle frosted glass effect; dark enough not to blind |
| Panel border | `1px solid rgba(255, 255, 255, 0.15)` | Soft separator from slide background |
| QR foreground (modules) | `#ffffff` | Maximum contrast against QR background |
| QR background | `#1e1e1e` | Near-black; matching app background |
| URL label text | `#aaaaaa` | Subdued — it is secondary to the QR |
| URL label font-size | `0.7rem` | Small; the QR is the primary element |

> **Note on QR contrast:** The `QRCodeSVG` component exposes `fgColor` and
> `bgColor` props. Set `fgColor="#ffffff"` and `bgColor="#1e1e1e"` to achieve a
> white-on-dark code. This is scan-safe on most phone cameras. If testing reveals
> scan failures on low-end phone cameras, swap to `fgColor="#1a1a1a"` on
> `bgColor="#ffffff"` (dark-on-white) — phones universally handle this.

### CSS Classes (additions to `index.css`)

```css
/* ─── QR Code Overlay ───────────────────────────────────────────────────── */
.qr-overlay {
  position: fixed;
  top: 0;
  right: 2rem;
  bottom: 0;
  display: flex;
  align-items: center;
  pointer-events: none;
  z-index: 10;
}

.qr-panel {
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  max-width: 256px;
}

.qr-url-label {
  font-size: 0.7rem;
  color: #aaaaaa;
  text-align: center;
  word-break: break-all;
  line-height: 1.4;
  user-select: text;
}
```

### Responsive Behavior

The overlay is designed for a projected or large-screen presenter view. No
special mobile breakpoints are required for the presenter view — it is not
intended to be used on a phone. However, to prevent the panel from overflowing
on very narrow screens (< 600px wide), add:

```css
@media (max-width: 600px) {
  .qr-overlay {
    right: 0.5rem;
  }

  .qr-panel {
    padding: 0.75rem;
  }
}
```

---

## Business Rules and Invariants

1. **First slide only.** The QR code renders if and only if `currentIndex === 0`
   in `SlideViewer`. There is no configuration to enable it on other slides; this
   is a hard rule.

2. **Presenter view only.** `QRCodeOverlay` is never imported or referenced in
   `AudienceView` or any audience-facing component.

3. **URL reflects current origin.** The URL encoded in the QR is always derived
   from `window.location.origin` at render time. If the presenter later moves the
   tab (e.g. changes port), the QR on slide 0 will reflect the new origin on
   re-render.

4. **No backend dependency.** The QR feature does not introduce any new API
   endpoints, WebSocket messages, or server state. Its only runtime dependency is
   the client-side QR library.

5. **No animation on appear/disappear.** The overlay mounts and unmounts without
   fade or transition effects. This keeps the implementation simple and avoids
   distracting motion during slide navigation.

6. **URL label is the full URL.** The label beneath the QR always shows the
   complete join URL (not a short URL, path-only string, or hostname-only string).
   This lets technically-minded audience members type it manually if camera
   scanning fails.

7. **QR code is not interactive.** The QR SVG is not a link or button. Clicking
   or tapping it on the presenter's screen does nothing.

---

## Testing Strategy

### Unit Tests — `QRCodeOverlay`

| Test | What to assert |
|---|---|
| Renders an `<svg>` element | SVG is present in the DOM after mounting with a valid `url` prop |
| Renders the URL label | The `url` string appears in the document |
| Accepts a custom `size` prop | The SVG's `width` and `height` attributes reflect the given size |

Use a mock for `qrcode.react` if the test environment cannot render SVG (e.g.,
jsdom). The mock need only render `<svg data-testid="qr-svg" />` — the library
itself does not need to be tested.

### Unit Tests — `SlideViewer` (QR conditions)

| Test | Setup | Expected |
|---|---|---|
| QR visible on slide 0 | Slides loaded, `currentIndex = 0` | `QRCodeOverlay` in the DOM |
| QR hidden on slide 1 | Slides loaded, `currentIndex = 1` | `QRCodeOverlay` **not** in the DOM |
| QR hidden while loading | `loading = true` | `QRCodeOverlay` **not** in the DOM |
| QR hidden on error | `error = "..."` | `QRCodeOverlay` **not** in the DOM |
| QR hidden on empty slides | `slides = []` | `QRCodeOverlay` **not** in the DOM |
| QR reappears on back-navigation | Navigate to slide 1, then back to 0 | `QRCodeOverlay` re-mounts |

### URL Construction Test

| Test | Condition | Expected `url` prop value |
|---|---|---|
| Localhost dev | `window.location.origin = "http://localhost:5173"`, `id = "demo"` | `"http://localhost:5173/presentations/demo/audience"` |
| LAN IP | `window.location.origin = "http://192.168.1.10:5173"`, `id = "slides"` | `"http://192.168.1.10:5173/presentations/slides/audience"` |
| Production HTTPS | `window.location.origin = "https://present.example.com"`, `id = "keynote"` | `"https://present.example.com/presentations/keynote/audience"` |

Mock `window.location.origin` in tests using `Object.defineProperty` or
`vi.stubGlobal` (Vitest) / `jest.spyOn` (Jest).

### Manual Smoke Test

1. Start the dev server bound to the machine's LAN IP (e.g.
   `vite --host 0.0.0.0`).
2. Open `http://<LAN-IP>:5173/presentations/demo` on the presenter's machine.
3. Verify QR panel is visible on the right side of the screen.
4. Scan the QR code with a phone on the same Wi-Fi network.
5. Phone browser navigates to `http://<LAN-IP>:5173/presentations/demo/audience`.
6. Press `→` on the presenter machine; QR panel disappears.
7. Press `←`; QR panel reappears.
8. Open `AudienceView` directly in a desktop browser; confirm no QR code is
   visible anywhere.

---

## Dependencies

### What This Feature Depends On

| Dependency | Why |
|---|---|
| `SlideViewer` component | QR overlay is rendered inside it |
| `currentIndex` state in `SlideViewer` | Controls visibility |
| `useParams` (`id`) in `SlideViewer` | Provides the presentation ID for URL construction |
| `window.location.origin` (browser API) | Constructs the base URL |
| `qrcode.react` (new npm package) | Client-side QR generation |

### What Depends on This Feature

Nothing currently depends on `QRCodeOverlay`. Future specs may reference it if,
for example, the audience join URL needs to be displayed in another context (e.g.,
a "share" modal), but those would be new features, not dependencies of this spec.

### Relationship to WebSocket Infrastructure

The QR code feature has **no runtime dependency** on WebSocket infrastructure. It
renders before any audience member has connected and does not consume or emit any
WebSocket messages. The features coexist in `SlideViewer` independently.

---

## Out of Scope

The following items are explicitly excluded from this specification. They may be
addressed in future specs.

- **Custom QR styling** — dot shapes, embedded logos, gradient colors, or any
  visual customization beyond foreground/background color.
- **Short URL generation** — the QR code always encodes the full URL. No URL
  shortening service is integrated.
- **Scan analytics** — the system does not track how many times the QR code is
  scanned, from what devices, or at what time.
- **QR code on every slide** — the QR appears only on slide 0. Showing it on
  subsequent slides, as a persistent sidebar element, or as a togglable overlay
  is out of scope.
- **Printable QR** — generating a downloadable image or PDF of the QR code for
  distribution outside the live presentation.
- **Dynamic QR** — a QR code that changes based on the current slide (e.g.,
  encoding a per-slide poll URL). This would require a separate spec.
- **QR error correction tuning** — the default error correction level (`L`, `M`,
  `Q`, or `H`) provided by `qrcode.react` is acceptable. No custom level is
  specified.
