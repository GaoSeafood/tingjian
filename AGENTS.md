# Agent handoff notes

## Project map

- This repository owns the web transcription service. The separately built desktop batch downloader lives in `GaoSeafood/tingjian-desktop`; do not add Electron builds or desktop runtime data here. Keep the web service's existing download task type intact.

- `frontend/`: React + Vite single-page application.
- `backend/app/main.py`: FastAPI routes, authentication, task/history APIs, and static frontend serving.
- `backend/app/jobs.py` and `backend/app/worker.py`: queued transcription, AI, cleanup, and download jobs.
- `backend/app/services/`: ASR, LLM, media/yt-dlp, and visual-analysis integrations.
- `docker-compose.yml`: web, workers, PostgreSQL, and Redis services.

Read `README.md` for the product overview and setup instructions before making larger changes.

## Product rules to preserve

- Creating a transcription task should only transcribe; highlights, visual analysis, and rewriting are explicit user actions.
- Video downloads are a separate task type from transcription.
- Tasks and history must remain scoped to their owning user. Do not weaken authorization checks.
- Source media is temporary and cleaned according to the configured retention policy; preserve cleanup behavior when changing task lifecycle code.
- Database schema changes must be additive and compatible with existing installations. Never delete or recreate production volumes.
- API credentials belong in local `.env` or the encrypted admin provider settings, never in source code, fixtures, screenshots, or commits.

## Validation

- Frontend: `npm --prefix frontend ci && npm --prefix frontend run build`
- Backend syntax: `python -m compileall -q backend/app`
- For deployment, update app/worker containers without removing PostgreSQL, Redis, or media volumes; keep the server's `.env` untouched.

## Repository hygiene

- Keep `.env`, runtime data, generated `output/`, browser profiles, build output, and Python caches out of Git.
- Do not add credentials or user media to logs, screenshots, or test fixtures.
