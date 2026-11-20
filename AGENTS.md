# Project overview

Fast Transcriber is a local, single-user MP3-to-TXT app. Keep it small: React with Vite and plain CSS, FastAPI, faster-whisper, and files on disk. No hosted services, accounts, database, or additional worker infrastructure are needed.

## Setup and commands

- Prerequisites: Node.js 22.12+ and uv.
- `npm start` installs locked dependencies, builds the frontend, and serves everything at http://127.0.0.1:8000. uv installs Python 3.12 automatically.
- `npm test` syncs Python development dependencies and runs `pytest` through the repository environment helper.
- `npm run build` verifies the production frontend build after dependencies are installed.
- `npm --prefix frontend run dev` starts optional Vite hot reload with `/api` proxied to the backend.
- After changing dependency declarations, regenerate and commit `uv.lock` or `frontend/package-lock.json`. Use `scripts/environment.mjs` for uv commands so caches and managed Python stay inside the repo.
- Keep PyAV below 19 while using faster-whisper 1.2.1: its decoder passes `metadata_errors`, which PyAV 19 removed. The native decoder regression test must pass before changing this constraint.

## Layout and conventions

- `backend/main.py`: API, disk-backed metadata, one background transcription process. Python functions use snake_case; validate input at API boundaries.
- `backend/tests/`: deterministic offline pytest tests. Substitute a model or drive the worker directly; normal tests must not fetch models.
- `frontend/src/main.jsx`: functional React UI, relative `/api` URLs, no router or state library. Keep file inputs, buttons, progress, and errors accessible.
- `frontend/src/styles.css`: responsive styles with system fonts; no remote fonts or analytics.
- `scripts/`: Node startup helpers. `npm start` must remain the complete end-user start command.

## Correctness and privacy

- Run `npm test` and `npm run build` for relevant changes. Investigate failures before finishing. For changes to real inference, also check a playable MP3 with an actual model when available; distinguish simulated tests from real inference.
- Long recordings must consume the full faster-whisper segments generator. Never add a 30-minute cutoff or put inference inside an HTTP request.
- Keep one inference worker and CPU INT8 defaults for predictable local resource use. The API must remain responsive while inference runs.
- Keep uploads chunked on disk, use generated UUID directories, and never trust a supplied filename as a filesystem path.
- Preserve atomic metadata/transcript replacement, actionable failures, refresh recovery, and completed UTF-8 downloads.
- Stop the background process during server shutdown; mark interrupted jobs as failed on the next start.
- Bind to loopback. Do not add public hosting, telemetry, cloud transcription, or audio transmission.
- Runtime data and dependencies belong in ignored repo-local `.data/`, `.cache/`, `.python/`, `.venv/`, `frontend/node_modules/`, or `frontend/dist/`. Standard `__pycache__/` and `.pytest_cache/` directories are also ignored. Never commit recordings or transcripts.

This file follows the [AGENTS.md format](https://agents.md/): keep agent setup, test commands, conventions, and project constraints here; keep end-user instructions in README.md.
