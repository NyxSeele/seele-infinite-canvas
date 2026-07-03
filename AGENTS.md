# AGENTS.md

## Cursor Cloud specific instructions

AI Studio is a two-tier app: a **FastAPI backend** (`backend/`, port `7788`) and a **React 19 + Vite frontend** (`frontend/`, dev port `8173`). Redis is used for collab/rate-limiting/WS broadcast; a local `redis-server` on `6379` is installed by the update script and the backend degrades gracefully if Redis is absent. The dev database is SQLite (`backend/aistudio.db`) by default. Standard commands live in `frontend/package.json` scripts, `backend/requirements.txt`, `backend/alembic.ini`, and `DEPLOY.md`.

### Environment / secrets (non-obvious)
- The backend **refuses to start** unless `backend/.env` sets a real `JWT_SECRET` (>=16 chars, not a placeholder from `WEAK_JWT_SECRETS` in `backend/core/config.py`). This file is gitignored, so it must be recreated on a fresh VM — the update script generates it if missing.
- Seeding dev accounts (`admin`, `testuser`, `testuser2`) requires `SEED_ADMIN_PASSWORD` / `SEED_TESTUSER_PASSWORD` / `SEED_TESTUSER2_PASSWORD` in `backend/.env`; seeding raises if they are empty. Seeding only runs when `APP_ENV=development`. The generated passwords are printed to the update-script output and stored in `backend/.env` — read them there to log in.
- Set `AGENT_MOCK_GENERATION=true` in `backend/.env` for E2E testing without a GPU/ComfyUI (real image/video generation needs an external ComfyUI at `COMFYUI_URL` plus `DASHSCOPE_API_KEY`/`DEEPSEEK_API_KEY` for LLM features). These are optional and not required to boot the app or run the canvas CRUD flow.

### Running services (from `/workspace`)
- Python deps live in the repo-root venv at `/workspace/.venv` (NOT `backend/.venv`). Use `/workspace/.venv/bin/...`.
- **First-time DB setup (required on a fresh VM, not done by the update script):** `cd backend && /workspace/.venv/bin/alembic upgrade head && /workspace/.venv/bin/python init_db.py` (runs migrations 001-021, then create_all + seeds `admin`/`testuser`/`testuser2`). Idempotent; the SQLite file `backend/aistudio.db` is gitignored.
- **Redis** (installed by the update script but not started by it): start with `redis-server --port 6379` in the background (e.g. a tmux session) before the backend if you want `redis:true`.
- Backend: `cd backend && /workspace/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 7788` (add `--reload` for hot reload). Health check: `GET /api/health` returns `{"status":"ok","env":"development","redis":true}`.
- Frontend: `cd frontend && npm run dev` → http://127.0.0.1:8173 (proxies API to `http://127.0.0.1:7788` via `frontend/.env.development`).

### Testing / lint (non-obvious)
- Backend tests: `cd backend && /workspace/.venv/bin/python -m pytest tests/ -q` (42 tests). `pytest` is a test-only dependency not in `requirements.txt`; the update script installs it.
- `python-multipart` is required at runtime (FastAPI form/upload endpoints) and was added to `backend/requirements.txt`; without it the app fails to import.
- Frontend lint: `cd frontend && npm run lint`. NOTE: the repo currently has many pre-existing ESLint errors (~282), so this command exits non-zero on a clean checkout — that is the repo's existing state, not a setup problem.
- There is no frontend build/test issue: `npm run build` produces `dist/`.
