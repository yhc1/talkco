# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: FastAPI service, SQLite access, OpenAI provider adapters, and backend tests.
- `frontend/`: iOS app (`TalkCo`) built with SwiftUI plus unit tests in `TalkCoTests`.
- `shared/`: cross-platform JSON constants (`constants.json`, `topics.json`) consumed by both backend and frontend.
- Root docs: `CLAUDE.md` defines product-level behavior; `backend/CLAUDE.md` and `frontend/CLAUDE.md` define implementation details.

## Build, Test, and Development Commands
- Backend run (from `backend/`): `python main.py`  
  Starts FastAPI via Uvicorn on `http://0.0.0.0:8000`.
- Backend tests (from `backend/`): `python -m pytest tests/ -v`  
  Runs async pytest suite (`pytest.ini` sets `asyncio_mode=auto`).
- Frontend tests (from `frontend/`): `xcodebuild test -project TalkCo.xcodeproj -scheme TalkCo -destination 'platform=iOS Simulator,name=iPhone 15'`  
  Runs Swift unit tests in `TalkCoTests`.
- Optional project regeneration (from `frontend/`): `xcodegen generate`  
  Rebuilds Xcode project from `project.yml` when project config changes.

## Coding Style & Naming Conventions
- Python: 4-space indentation, type hints on public functions, `snake_case` for functions/variables, `PascalCase` for classes.
- Swift: 4-space indentation, `camelCase` members, `PascalCase` types/files (for example `ConversationViewModel.swift`).
- Prefer enums/constants over raw strings for domain values (session mode/status/issue dimension). Update `shared/constants.json` first, then synced enums in backend and frontend.

## Testing Guidelines
- Backend tests live in `backend/tests/` and use `test_*.py` naming.
- Frontend tests live in `frontend/TalkCoTests/` and group by feature (`Models/`, `Services/`, `ViewModels/`).
- Add or update tests for each behavior change, especially API contract changes and session/review flows.
- No fixed coverage threshold is configured; keep changed code paths exercised.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history: `feat: ...`, `refactor: ...`, `fix: ...`.
- Keep commits focused (single concern) and describe user-visible impact.
- PRs should include: concise summary, test evidence (commands run), linked issue/task, and screenshots/video for UI changes.

## Configuration & Security Tips
- Backend settings are read from `backend/.env` (`OPENAI_API_KEY`, model names, `DB_PATH`).
- Do not commit secrets or local database artifacts with sensitive data.
