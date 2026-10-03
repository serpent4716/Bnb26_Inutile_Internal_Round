# CLAUDE.md — CreatorAi

This file gives Claude Code standing context for this repo. Read it at the start of every session.

## Project

CreatorAi is an AI-powered creator operating platform built for a hackathon. Core loop: **script + raw footage → transcription → script-to-footage alignment → AI-picked short clips → editable Edit Decision List (EDL) → platform-adapted renders + hooks/captions.**

Full specs live in these docs. Read the relevant one before building a feature:
- `ARCHITECTURE.md`: stack, folder structure, pipeline, EDL format
- `DATABASE_SCHEMA.md`: MongoDB collections (source of truth for models)
- `EXTERNAL_APIS.md`: Gemini, Whisper (Groq / local), Cloudinary
- `FEATURES.md`: implementation spec + acceptance criteria for F1–F8
- `API_ENDPOINTS.md`: REST routes (source of truth for the API contract)
- `BUILD_PLAN.md`: priorities (P0 → P1 → P2) and phases

## Stack

- **Backend:** Python 3.11+, FastAPI, Motor (async MongoDB), Pydantic v2
- **Frontend:** React (Vite), Tailwind, Zustand, axios, Recharts, @dnd-kit/core
- **DB:** MongoDB Atlas (Atlas Vector Search for semantic search)
- **Media:** FFmpeg (subprocess or ffmpeg-python), MediaPipe, OpenCV, pydub, rapidfuzz
- **AI:** `google-genai` SDK (Gemini text/vision/embeddings), Groq Whisper API with `faster-whisper` local fallback
- **Storage:** abstracted in `services/storage.py`, `STORAGE_BACKEND=local|cloudinary`

## Non-negotiable rules

1. **AI never outputs a baked video.** Every AI edit is written into the clip's `edl` JSON. Video is rendered only on explicit export (`POST /clips/{id}/render`).
2. **Every EDL change is versioned.** Push to `edl_versions` with `edited_by: "ai" | "user"`.
3. **Cut boundaries always snap to word timestamps** from the transcript. Never cut mid-word.
4. **All LLM calls return structured JSON** (Gemini `response_mime_type="application/json"` + schema). Validate with Pydantic. Retry once on parse failure.
5. **Cache every AI output in MongoDB.** Never regenerate on a page load or GET request.
6. **Long work runs as a background job** that updates the `jobs` collection (`status`, `current_step`, `progress`). Routes return `{job_id}` immediately.
7. **All external services sit behind a service module** (`services/llm.py`, `services/transcription.py`, `services/storage.py`) so they can be swapped or mocked.
8. **Secrets only from `.env`** via `config.py`. Never hardcode keys. Keep `.env.example` updated.
9. Collections and field names must match `DATABASE_SCHEMA.md`. Routes must match `API_ENDPOINTS.md`. If a change is needed, update the doc in the same change.

## Coding conventions

- Backend: async everywhere, type hints, routers thin with logic in `services/`, one Pydantic model file per collection in `models/`.
- Convert Mongo `ObjectId` to string in responses via a shared helper.
- Errors: `HTTPException` with `{detail, code}`.
- Frontend: functional components + hooks, API calls only through `src/api/`, global state in Zustand stores.
- Keep FFmpeg command builders in pure functions that return arg lists, so they can be unit-tested and printed for debugging.

## Commands

```bash
# backend
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000
pytest

# frontend
cd frontend && npm run dev     # http://localhost:5173
```

## Workflow for Claude Code

- Before a feature, read its section in `FEATURES.md` and restate the acceptance criteria.
- Build in small, runnable steps. After each step, run it (start the server, hit the endpoint, run tests) before moving on.
- Don't start P2 features until the P0 checkpoint in `BUILD_PLAN.md` passes.
- When something is mocked (e.g. analytics), label it clearly in code with `# MOCK:`.
- At the end of each task, summarize what was built, how to test it, and anything left undone.