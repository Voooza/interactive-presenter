# Bugs of Interactive Presenter: War Stories from Development

# Bug: Markdown Tables Not Rendering

**Issue:** ip-xha

- `ReactMarkdown` used without the `remark-gfm` plugin
- GFM pipe-table syntax rendered as raw text on every slide with a table
- Pipe characters everywhere, zero tables

**Fix:** Install `remark-gfm`, pass as plugin to all `ReactMarkdown` instances

```
| Before | After |
|--------|-------|
| raw text | actual table |
```

# Bug: Audience Joins Mid-Poll, Sees Nothing

**Issue:** ip-1w1

- `poll_opened` message only fired on slide transitions (`_handle_poll_lifecycle`)
- Presenter already on a poll slide? New audience members never saw it
- You joined, you saw nothing, you were confused

**Fix:** In `connection_manager.py connect()`, after sending `connected` payload,
check `room.active_poll` and immediately send `poll_opened` to the new connection

# Bug: Companion Actions Not Reflected on Presenter Page

**Issue:** ip-8oh — the double-bug special

- **Bug 1:** Backend rejected new presenter WS connection on browser refresh —
  old disconnect hadn't been processed yet (race condition, code 4002)
- **Bug 2:** Frontend didn't check WS close codes — retried forever on permanent
  failures, causing the infamous yellow blinking indicator

**Fix:** Backend replaces old presenter instead of rejecting; frontend stops
reconnecting on permanent close codes

<!-- poll
Which bug would have annoyed you most?
- The invisible poll (audience joins and sees nothing)
- The blinking yellow light of doom (endless WS reconnect)
- Raw pipe characters instead of a table
- 404 on the companion page
-->

# Bug: Companion Page 404 in Production

**Issue:** ip-023

- Production companion page returned 404
- Route was missing in the prod configuration
- Worked fine locally, exploded in production (classic)

**Fix:** Added missing route to prod config; verified with pytest, ruff, npm build

# Bonus Round: The Meta-Bug

The `test_command` was configured as `go test ./...`

On a **Python/React** project.

- Refinery couldn't run tests
- Nobody noticed for days
- The CI was confidently doing nothing

**Lesson:** Always verify your toolchain config matches your actual stack

# Every Bug Made the System More Robust. Ship It.

- Tables now render (users can read data)
- Late joiners see polls (nobody left behind)
- Presenter page stays in sync (no more blinking yellow doom)
- Companion page loads in prod (the whole point)
- Tests actually run (revolutionary)

*The best bugs are the ones you fix.*
