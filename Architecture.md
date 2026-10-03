# Architecture

## High-level components

```
┌──────────────────────┐        ┌───────────────────────────────┐
│  React Frontend      │  REST  │  FastAPI Backend              │
│  - Asset library     │◄──────►│  - Routers (assets, scripts,  │
│  - Script editor     │        │    clips, workflow, insights) │
│  - Timeline editor   │        │  - Job runner (background)    │
│  - Kanban workflow   │        └──────┬───────────┬────────────┘
│  - Insights dashboard│               │           │
└──────────────────────┘               │           │
                                       ▼           ▼
                         ┌────────────────┐  ┌──────────────────────┐
                         │ MongoDB Atlas  │  │ Processing Pipeline  │
                         │ + Vector Search│  │ FFmpeg / Whisper /   │
                         └────────────────┘  │ MediaPipe / Gemini   │
                                             └──────────┬───────────┘
                                                        ▼
                                             ┌──────────────────────┐
                                             │ Cloudinary / local   │
                                             │ media storage        │
                                             └──────────────────────┘
```

## Backend folder structure

```
backend/
  app/
    main.py
    config.py               # env vars
    db.py                   # Motor (async Mongo) client
    models/                 # Pydantic models matching DATABASE_SCHEMA.md
    routers/
      assets.py
      scripts.py
      projects.py           # workflow / kanban
      processing.py         # trigger pipeline, job status
      clips.py              # EDL CRUD + render
      generate.py           # hooks, captions, scripts
      insights.py
    services/
      storage.py            # upload/download (Cloudinary or local)
      transcription.py      # Whisper
      alignment.py          # script ↔ transcript matching
      clip_finder.py        # LLM picks highlight moments
      edl.py                # build/validate edit decision lists
      renderer.py           # EDL → MP4 via FFmpeg
      reframe.py            # 16:9 → 9:16 with face tracking
      llm.py                # Gemini wrapper (text + vision + embeddings)
      tagging.py            # auto-tag assets from frames
      insights.py
    jobs/
      runner.py             # background job execution + status updates
  requirements.txt
  .env.example
```

## Frontend folder structure

```
frontend/src/
  pages/
    Dashboard.jsx
    Library.jsx             # asset management + semantic search
    ProjectBoard.jsx        # kanban workflow
    ProjectDetail.jsx       # script + footage + generated clips
    ClipEditor.jsx          # timeline editor for EDLs
    Insights.jsx
  components/
    Timeline/               # tracks, trim handles, caption blocks
    VideoPlayer.jsx         # previews EDL by seeking source video
    UploadDropzone.jsx
    HookCard.jsx
  store/                    # Zustand stores
  api/                      # axios client
```

## The processing pipeline

Triggered when a project has both a script and footage. Each step updates a `jobs` document so the UI can show progress.

```
1. INGEST        upload → storage → ffprobe metadata (duration, fps, resolution)
2. EXTRACT       FFmpeg: audio (16kHz mono wav) + keyframes (1 every 2–3s)
3. TRANSCRIBE    Whisper → segments + word-level timestamps → `transcripts`
4. TAG           keyframes → Gemini Vision → tags/scene descriptions → asset.tags
5. EMBED         transcript chunks + tags → embeddings → vector index
6. ALIGN         script lines ↔ transcript segments → `alignments`
                 (detect retakes: same line spoken multiple times → keep best)
7. FIND CLIPS    LLM reads timestamped transcript → candidate moments + scores
8. BUILD EDL     each candidate → EDL JSON (cuts, silence removal, captions, zooms)
9. GENERATE      hooks, titles, captions, hashtags per platform
10. RENDER       (on demand) EDL → FFmpeg → MP4 (16:9 or 9:16 reframed)
```

### Key design decision: EDL, not baked video

AI never outputs a final video directly. It outputs an **Edit Decision List**:

```json
{
  "source_asset_id": "...",
  "aspect_ratio": "9:16",
  "segments": [ { "start": 12.40, "end": 18.90 }, { "start": 21.10, "end": 41.00 } ],
  "captions": [ { "start": 0.0, "end": 1.8, "text": "I lost ₹50,000", "style": "bold" } ],
  "zooms":    [ { "start": 4.0, "end": 6.0, "scale": 1.2 } ],
  "crop_track": [ { "t": 0.0, "x_center": 0.52 } ],
  "overlays": []
}
```

- The **frontend previews** it by playing the source video and skipping between segments, with captions as HTML overlays, so no rendering is needed while editing.
- The **backend renders** only on export.
- This satisfies the "AI edits remain editable" requirement.

## Background jobs

For a hackathon, use FastAPI `BackgroundTasks` plus a `jobs` collection for status, which needs no Redis. If processing gets heavy or you need retries, switch to RQ or Celery with Redis.

Frontend polls `GET /jobs/{id}` every 2s, or you can use WebSockets if there's time.