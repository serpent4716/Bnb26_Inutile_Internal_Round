# CreatorAi

An AI creator operating platform: **script + raw footage → transcript → script alignment → AI-picked short clips → editable edits → platform-ready videos and copy → insights**. AI does the repetitive work; every AI edit stays editable (clips are Edit Decision Lists, not baked video).

## What's in it

| Area | What it does |
|---|---|
| Library | Upload footage; transcribed with word timestamps, described by Gemini Vision, searchable by what was said ("the bit about index funds" jumps to the second). |
| Script understanding | Matches every script line to the footage, finds retakes and picks the clean one, flags missing lines and unscripted ad-libs, builds a rough cut. |
| Clips | Gemini picks 15-60s moments; cuts snap to word boundaries; fillers, retakes and long pauses removed; word-chunked captions, zoom punches, speaker-tracked 9:16 crop. |
| Clip editor | Live preview, hook picker (5 hook types), Descript-style transcript editing, segment timeline, undo. |
| Platforms | "Adapt for all": Shorts / Reels / TikTok / YouTube / LinkedIn / X versions (aspect, captions, length) with copy in each platform's style; MP4 export. |
| Workflow | Kanban from idea to published; stages auto-advance; mock publish. |
| Insights | Performance charts (sample data), real production stats, time saved by AI, AI-written insight cards. |

Stack: React (Vite) + Tailwind + Zustand · FastAPI + Motor · MongoDB Atlas (+ Vector Search) · FFmpeg · MediaPipe · faster-whisper / Groq Whisper · Gemini.

## Setup

**Prerequisites:** Python 3.10+, Node 20+, FFmpeg on PATH (`ffmpeg -version`), a MongoDB Atlas cluster (free M0 works), a Gemini API key. A Groq key is optional (faster transcription).

```bash
# backend
cd backend
python -m venv venv
venv\Scripts\activate            # Windows (cmd/PowerShell)
# source venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
copy .env.example .env           # cp on macOS / Linux, then fill it in (below)
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

Check `http://localhost:8000/api/v1/health` shows `{"db":"ok","ffmpeg":true}`.

> **Windows:** if you installed FFmpeg while your editor was open, its terminals keep the old PATH and `/health` shows `ffmpeg:false`. Restart the editor, or in that terminal: `set "PATH=%PATH%;<ffmpeg bin folder>"`.

### Environment variables (`backend/.env`)

| Variable | Required | Notes |
|---|---|---|
| `MONGODB_URI` | yes | Atlas connection string including the database name, e.g. `.../creatorai?...` |
| `JWT_SECRET` | yes | any long random string: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GEMINI_API_KEY` | yes | Google AI Studio. Text, vision and embeddings. |
| `GEMINI_TEXT_MODEL` | no | default `gemini-3.5-flash` |
| `GEMINI_FALLBACK_MODELS` | no | tried in order when a model is out of quota; default `gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-flash-lite-latest` |
| `GROQ_API_KEY` | no | Groq Whisper. Without it (or if it fails) transcription runs locally with faster-whisper. |
| `WHISPER_LOCAL_MODEL` | no | `tiny` / `base` (default) / `small` / `medium` |
| `STORAGE_BACKEND` | no | `local` (default, files under `backend/media/`) or `cloudinary` |
| `CLOUDINARY_*` | if cloudinary | cloud name, key, secret |
| `CORS_ORIGINS` | no | default `http://localhost:5173` |
| `ENABLE_DEV_ENDPOINTS` | no | `true` enables `/dev/seed-analytics` and `/dev/reindex-embeddings`; set `false` in production |
| `PEXELS_API_KEY` | no | unused for now (B-roll suggestions) |

### Semantic search index (Atlas UI, one time)

Atlas → your cluster → **Atlas Search** → **Create Search Index** → **Atlas Vector Search** → **JSON Editor**. Database: yours, collection `embeddings`, index name **`embeddings_vector`**:

```json
{
  "fields": [
    { "type": "vector", "path": "vector", "numDimensions": 768, "similarity": "cosine" },
    { "type": "filter", "path": "user_id" }
  ]
}
```

Until it's active, search uses a keyword index over the same transcript chunks (results say `match: "keyword"`); it switches to semantic automatically.

## Demo data

Loads one complete project by running the real pipeline (transcribe, align, clips, hooks, adapt, renders) plus kanban cards and **mock** analytics:

```bash
cd backend
python -m scripts.seed_demo                                     # sample footage in backend/demo/
python -m scripts.seed_demo --video my_take.mp4 --script my_script.txt
```

Sign in as **`demo@creatorai.dev` / `demo-pass-2026`**. Re-running wipes and rebuilds only that account. It takes ~35s and ~8 Gemini calls.

The bundled `backend/demo/demo.mp4` is placeholder footage (a voice track over a plain card, no face). For the real demo, record yourself following `backend/demo/script.txt` with 2-3 deliberate retakes, a few "umm"s and one unscripted story, then seed with `--video`. Face tracking needs a face in shot.

## Demo flow (~4 min)

Timings measured on the 97s sample footage (Groq + Gemini, local storage):

| # | Show | What to click | Time |
|---|---|---|---|
| 1 | Problem | slides | |
| 2 | Upload | Projects → new project → paste script → drop footage → **Match script to footage**; the stepper shows each stage | script labelled 2.4s · upload processed 13s · align + clips + edits 10s |
| 3 | Script understanding | coverage, retakes with take picker, missing lines, ad-libs; click a line to jump | instant |
| 4 | Clips | **Clips** tab: ranked clips with reasons and scores → **Edit**: 9:16 preview with captions and tracked crop | instant |
| 5 | Creator control | click a word to cut it, hover the timeline and cut a segment, **Undo**, pick a different hook, **Export MP4** | edits ~0.2-0.8s · render 1.5-3.5s per 15-30s clip |
| 6 | Adapt | **Adapt for all** → platform tabs, each with preview, editable copy, export | ~4-5s for 6 platforms |
| 7 | Platform | drag the card on the kanban, **Publish (mock)**; Library search for a spoken phrase; Insights | search ~1.3s |
| 8 | Close | Dashboard: time saved | |

Render times seen while testing: 9:16 Shorts 1.4-3.5s, 1:1 LinkedIn 1.4-2.3s, 16:9 YouTube ~2s (15-30s clips, `veryfast` x264).

**Before judging:** pre-process the demo footage (seed it), and only run one live generation. Free-tier Gemini allows ~20 requests per model per day and a full project run uses 4-8, so enable billing or keep a second key. If a model runs out, the app falls through the fallback list; if all are out, the UI says so instead of failing silently.

## Tests

```bash
cd backend && python -m pytest       # alignment, clip finding, EDL building, rendering commands, search, insights
```

## Docs

| File | What it covers |
|---|---|
| `Architecture.md` | Stack, components, pipeline, EDL format |
| `Database schema.md` | MongoDB collections and fields (source of truth) |
| `Api endpoints.md` | REST routes (source of truth) |
| `External apis.md` | Third-party APIs and free tiers |
| `Features.md` | Feature specs F1-F8 |
| `Build plan.md` | Priorities and the demo script |
