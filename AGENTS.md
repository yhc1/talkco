# Repository Guidelines

## Project Structure & Module Organization
- `backend/` — FastAPI service, OpenAI providers, SQLite storage, and pytest tests.
- `frontend/` — iOS app (SwiftUI) with models, services, view models, and views under `frontend/TalkCo/`.
- Root docs: `CLAUDE.md` (product context), `backend/CLAUDE.md`, `frontend/CLAUDE.md`

## Build, Test, and Development Commands
- Backend server:
  - `cd backend && source .venv/bin/activate && python main.py` — run API locally.
- Backend test client:
  - `cd backend && source .venv/bin/activate && python test_client.py` — end-to-end conversation flow.
- Backend tests:
  - `cd backend && source .venv/bin/activate && python -m pytest tests/ -v` — unit tests for review flow.
- Frontend app:
  - Open `frontend/TalkCo.xcodeproj` in Xcode and Run (iOS 17+).

## Coding Style & Naming Conventions
- Follow existing conventions in each module; keep files small and focused.
- Python: PEP 8 style, 4-space indent, snake_case for functions/vars, PascalCase for classes.
- Swift: SwiftUI + `@Observable`, standard Swift naming (camelCase, PascalCase types).
- No formatter/linter is configured; align with nearby code.

## Testing Guidelines
- Framework: pytest (`backend/pytest.ini` uses `asyncio_mode = auto`).
- Test naming: `test_*.py` in `backend/tests/`.
- Run tests via the pytest command above; add/adjust mocks for `chat_json` as needed.

## Commit & Pull Request Guidelines
- Commit messages follow `<type>: summary` (e.g., `<feature>: add review flow`).
- Prefer small, scoped commits; reference relevant files/paths in PR descriptions.
- For UI changes, include screenshots or a short video in the PR.

## Security & Configuration Tips
- Backend uses `.env` for `OPENAI_API_KEY`, `S2S_MODEL`, `CHAT_MODEL`, and `DB_PATH`.
- SQLite database defaults to `talkco.db` in `backend/`; don’t commit local DB files.
