# Gas Town: Multi-Agent Software Engineering

**How I stopped prompting one AI and started running a crew**

*vanispe / Voooza*

<!-- poll
- Yes, daily
- Tried it once or twice
- Not yet, but curious
- AI? In this economy?
-->

Have you used AI coding agents?

# The Problem with Solo Agents

You describe a task. The agent does it. You review. Repeat.

- Works fine for a bug fix
- Falls apart for "add four real-time features to a full-stack app"
- Serial by nature — one director, one actor
- The director ends up repainting every set, wiring every mic

**What if you could file work and have a crew run with it?**

# What Is Gas Town?

A multi-agent workspace manager. Think production company, not freelancer.

```
Town (/home/you/gt)
├── mayor/              ← Coordinator (you)
├── your-project/       ← A "rig"
│   ├── .beads/         ← Issue tracking
│   ├── polecats/       ← Worker agents
│   │   ├── chrome/     ←   (isolated git worktree)
│   │   └── rust/       ←   (isolated git worktree)
│   ├── refinery/       ← Merge queue
│   └── witness/        ← Lifecycle monitor
```

Each rig is a project. Each polecat is an autonomous worker with its own branch.

# The Agents

| Role | Job | Analogy |
|------|-----|---------|
| **Mayor** | Dispatches work, writes specs, reviews escalations | Project manager |
| **Polecats** | Autonomous workers — implement, test, commit | Developers |
| **Witness** | Monitors polecat health, catches failures | QA / ops |
| **Refinery** | Bisecting merge queue — merges clean work | CI/CD |
| **Convoy** | Batch tracking across rigs | Release manager |

Polecats get isolated git worktrees. They can't step on each other.

# Beads: Structured Issue Tracking

Beads is the issue system. Built for agents, not humans with browsers.

```bash
bd create "Add emoji reactions"     # File an issue
bd ready                            # Find unblocked work
bd update ip-abc --status=in_progress
bd close ip-abc                     # Done
```

- **Prefix routing**: `ip-abc` routes to the right rig automatically
- **Dependency management**: `bd dep add child parent` — "child needs parent"
- **Molecule workflows**: multi-step formula checklists attached to issues
- All stored in Dolt (version-controlled database)

# Day-to-Day: How I Actually Use It

Rigs are **docked** by default — idle, no agents running, no cost.

```
Morning:  gt wake interactive_presenter   # Spin up the rig
          bd create "Fix the QR URL"      # File work
          gt sling ip-xyz chrome          # Assign to a polecat

          ... polecat works autonomously ...
          ... refinery merges when ready ...

Evening:  gt dock interactive_presenter   # Shut it down
```

- I write specs and file beads. Polecats implement.
- Witness catches false completions. Refinery handles merges.
- I review escalations and fill gaps (CSS, integration, etc.)

# Case Study: This App

Interactive Presenter was built with Gas Town. Here's episode 04:

**The work:**
- 4 specs written in parallel (emoji, polls, Q&A, QR code)
- 4 beads filed, slung to polecats
- Each polecat: implement → test → commit → submit to merge queue

**What happened:**
- Emoji reactions: polecat "rust" — clean, 7 tests ✓
- Polls: polecat "chrome" — full stack, 18 tests ✓
- Q&A: polecat "nitro" — **closed with zero code changes** 🚫
- Witness caught it, escalated, re-filed to "rust" — 12 tests ✓
- QR code: landed last (narrative irony)

Tests went from 37 → 96 in one session.

# The Hardening Session (Episode 05)

Feature-complete ≠ working. Seven commits, all fixes:

- QR code pointed at wrong URL (route mismatch)
- Q&A form hidden under emoji bar (CSS overlap)
- Emoji allowlists diverged between frontend and backend
- WebSocket double-mount under React StrictMode
- Poll options rendered twice in slide content

**The lesson:** tests passed because they tested units, not journeys. No test said "scan QR → land on audience page → tap 💯 → see it float up."

The demo works before you demo it, and then it doesn't.

<!-- poll
- Happened to me last week
- I feel personally attacked
- My tests would have caught it
- Tests? What tests?
-->

# What Works

- Parallel feature development — real throughput gain
- Witness as safety net — caught a false completion before it became a hidden problem
- Refinery — autonomous merging without human babysitting
- Isolated worktrees — polecats can't corrupt each other's state

# What's Surprising

- The CSS gap — parallel agents all add class names, nobody writes the CSS
- False completions happen — agents can claim "done" with zero changes
- Integration bugs accumulate silently across agent boundaries

# Honest Tradeoffs

- Coordination overhead is real — specs must be precise
- The Mayor still does the unsexy work (gap patches, integration fixes)
- More infrastructure to maintain than a single-agent workflow

# What's Next

- **This presentation** was built by a Gas Town polecat (meta!)
- Multi-presentation support and presenter auth on the backlog
- Better integration testing — the episode 05 lesson
- Scaling to more rigs and larger projects

**The core insight:** the bottleneck isn't agent capability — it's coordination. Gas Town is an answer to "how do you manage a crew, not just an assistant?"

# Thank You

**Gas Town** — github.com/vanispe

Questions? Use the Q&A below. Or just send emoji reactions. I'll see them float up.
