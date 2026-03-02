# AGENTS.md — Coding Agent Guidelines

## Project Overview

Interactive Presenter: a web-based presentation tool where audiences participate
via emoji reactions, polls, Q&A, and more. Presentations are defined as Markdown
files (H1 headings separate slides). A QR code on the first slide links the
audience to an interactive companion page.

- **Backend:** Python
- **Frontend:** React
- **Database:** SQLite (file-based)

---

## Repository Structure

```
interactive_presenter/
├── AGENTS.md              # This file — agent guidelines
├── spec/                  # Project specifications and design docs
│   ├── mission_statement.md
│   └── tech_stack.md
├── blog/                  # Development blog (Org-mode format)
│   └── episode_01.org
├── backend/               # Python backend (planned)
└── frontend/              # React frontend (planned)
```

---

## Build / Lint / Test Commands

### Backend (Python)

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the backend server
python -m backend.main

# Run all tests
pytest

# Run a single test file
pytest tests/test_example.py

# Run a single test function
pytest tests/test_example.py::test_function_name

# Run tests with verbose output
pytest -v

# Run tests matching a keyword
pytest -k "keyword"

# Linting
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Formatting
ruff format .

# Check formatting without modifying
ruff format --check .

# Type checking
mypy backend/
```

### Frontend (React)

```bash
# Install dependencies
cd frontend && npm install

# Start dev server
npm run dev

# Build for production
npm run build

# Run all tests
npm test

# Run a single test file
npm test -- path/to/test.spec.ts

# Linting
npm run lint

# Formatting
npm run format
```

---

## Code Style Guidelines

### Python (Backend)

**Formatting & Linting:**
- Use `ruff` for both linting and formatting
- Target Python 3.11+
- Line length: 88 characters (ruff default)

**Imports:**
- Group imports in this order, separated by blank lines:
  1. Standard library
  2. Third-party packages
  3. Local/project imports
- Use absolute imports (`from backend.models import Slide`), not relative
- Let `ruff` sort imports automatically (`isort`-compatible rules)

**Naming Conventions:**
- `snake_case` for functions, methods, variables, and modules
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Prefix private/internal names with underscore (`_helper_func`)

**Type Annotations:**
- Add type hints to all function signatures (parameters and return types)
- Use modern syntax: `list[str]`, `dict[str, int]`, `str | None` (not `Optional`)
- Use `TypedDict` or dataclasses for structured data

**Docstrings:**
- Use triple double-quotes for all public functions, classes, and modules
- Follow Google-style docstring format:
  ```python
  def create_slide(content: str, order: int) -> Slide:
      """Create a new slide from markdown content.

      Args:
          content: Raw markdown string for the slide.
          order: Zero-based position in the presentation.

      Returns:
          A Slide instance ready for persistence.

      Raises:
          ValueError: If content is empty.
      """
  ```

**Error Handling:**
- Raise specific exceptions, never bare `raise` or `except Exception`
- Define custom exception classes in a `backend/exceptions.py` module
- Use early returns to reduce nesting
- Log errors before re-raising when appropriate

**General:**
- Prefer dataclasses or Pydantic models over plain dicts for structured data
- Keep functions short and focused (aim for < 30 lines)
- Write pure functions where possible; isolate side effects

### TypeScript / React (Frontend)

**Formatting & Linting:**
- Use ESLint + Prettier
- Line length: 100 characters

**Naming Conventions:**
- `camelCase` for variables, functions, hooks
- `PascalCase` for components, types, interfaces, and enums
- `UPPER_SNAKE_CASE` for constants
- Prefix custom hooks with `use` (e.g., `useReactions`)
- Name files after their default export: `SlideViewer.tsx`, `usePolls.ts`

**Types:**
- Use TypeScript strict mode
- Prefer `interface` for object shapes, `type` for unions/intersections
- Avoid `any`; use `unknown` if the type is truly unknown
- Export types alongside their related functions/components

**Components:**
- Use functional components with hooks (no class components)
- One component per file
- Co-locate component-specific styles, tests, and types

**Error Handling:**
- Use error boundaries for component tree failures
- Handle async errors with try/catch in async functions
- Display user-friendly error messages; log details to console

**Imports:**
- Group in order:
  1. React / framework imports
  2. Third-party libraries
  3. Project-internal imports (components, hooks, utils)
  4. Styles / assets

---

## Database

- SQLite via a Python library (e.g., `sqlite3` stdlib or an async driver)
- Migrations should be version-controlled and repeatable
- Keep the schema in a dedicated `backend/schema.sql` or migrations directory

---

## Blog

- Blog posts live in `blog/` and use Emacs Org-mode format (`.org`)
- Do not auto-generate or modify blog files unless explicitly asked

---

## General Principles

- Read `spec/` files before implementing any feature — they are the source of truth
- Prefer small, incremental commits with descriptive messages
- Do not commit secrets, credentials, or `.env` files
- When in doubt about a design choice, check the spec or ask the user
