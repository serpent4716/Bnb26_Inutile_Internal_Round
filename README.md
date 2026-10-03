# CreatorAi — AI-Powered Creator Operating Platform

One platform that takes a creator from **idea → script → raw footage → short clips → platform-ready posts → insights**, with AI handling the repetitive work and every AI edit staying editable.

## Core demo loop (build this first)

1. Creator uploads a **script** and **raw footage**.
2. System transcribes footage with word-level timestamps.
3. Transcript is **aligned to the script**; retakes and filler are detected.
4. AI picks the **best short-form moments** and scores them.
5. Clips are generated as an **Edit Decision List (EDL)**, a JSON timeline, not a baked video.
6. Creator tweaks cuts and captions in a timeline editor.
7. Clips are reframed to 9:16 and given **hooks and captions per platform**.
8. Export the final MP4s and move the content card to "Published".

## Docs in this repo

| File | What it covers |
|---|---|
| `ARCHITECTURE.md` | Tech stack, system components, processing pipeline |
| `DATABASE_SCHEMA.md` | MongoDB collections, fields, indexes |
| `EXTERNAL_APIS.md` | Every third-party API, why it's needed, free-tier notes |
| `FEATURES.md` | Implementation spec for all 8 features |
| `API_ENDPOINTS.md` | Backend REST routes |
| `BUILD_PLAN.md` | Priorities, team split, hour-by-hour plan, demo script |

## Tech stack (summary)

- **Frontend:** React (Vite) + Tailwind + Zustand
- **Backend:** Python FastAPI (Python is a must for FFmpeg, Whisper, MediaPipe and OpenCV)
- **Database:** MongoDB Atlas (with Atlas Vector Search)
- **Media processing:** FFmpeg, MediaPipe, OpenCV (local libraries, no API cost)
- **AI:** Gemini (LLM + vision + embeddings), Whisper (transcription)
- **Storage:** Cloudinary (or local disk for the demo)

## Quick start

```bash
# backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill keys (see EXTERNAL_APIS.md)
uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
```

FFmpeg must be installed and on PATH: `ffmpeg -version`.