# External APIs

## Summary

| # | API | Purpose | Required? | Free option |
|---|---|---|---|---|
| 1 | **Google Gemini API** | LLM (scripts, hooks, clip picking), vision (frame tagging), embeddings | ✅ Required | Free tier on Google AI Studio |
| 2 | **Speech-to-text (Whisper)** | Transcription with word timestamps | ✅ Required | Groq Whisper API (free tier) **or** run `faster-whisper` locally (no API) |
| 3 | **Cloudinary** | Media storage + thumbnails + delivery | ⚠️ Recommended | Free tier; or store on local disk for the demo |
| 4 | MongoDB Atlas | Database + vector search | ✅ (it's your DB) | M0 free cluster |
| 5 | Pexels API | Stock B-roll suggestions for script lines | Optional | Free |
| 6 | YouTube Data API v3 | Pull real analytics / publish | Optional | Free quota |

**Minimum: 2–3 external APIs** (Gemini + Whisper + storage). If you run Whisper locally and store files on disk, Gemini is the only paid-style API you need.

**Realistic hackathon set: 3** (Gemini, Groq Whisper, Cloudinary), plus MongoDB Atlas.

---

## Not APIs (local libraries, free, no keys)

| Library | Used for |
|---|---|
| **FFmpeg** (via `ffmpeg-python` or subprocess) | Cutting, concatenating, audio extraction, keyframes, burning captions, rendering |
| **MediaPipe / OpenCV** | Face detection → smart 9:16 crop tracking |
| **pydub / webrtcvad** | Silence detection |
| **rapidfuzz** | Fast fuzzy matching for script alignment |
| **faster-whisper** | Local transcription if you avoid the API |

---

## 1. Gemini API

One key covers three jobs:
- **Text:** `gemini-2.5-flash` (fast, cheap) for hooks, captions, clip selection. Use structured JSON output (`response_mime_type: "application/json"` + schema).
- **Vision:** send keyframes and get tags and scene descriptions.
- **Embeddings:** a text-embedding model for semantic search.

Gemini can also take a whole video file as input, which is a useful shortcut for visual understanding of short clips. For long footage, use keyframes, since it's cheaper and faster.

```python
# services/llm.py (sketch)
from google import genai
client = genai.Client(api_key=settings.GEMINI_API_KEY)

def generate_json(prompt: str, schema) -> dict:
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": schema},
    )
    return resp.parsed
```

Check current model names and free-tier limits in Google AI Studio before the event, because they change.

## 2. Whisper (transcription)

**Option A — Groq API (fastest, recommended):** `whisper-large-v3` / `whisper-large-v3-turbo`, very fast, free tier. Request `response_format="verbose_json"` and `timestamp_granularities=["word","segment"]`. There's a file size limit, so send extracted **16kHz mono audio**, not the video, and chunk long audio.

**Option B — OpenAI Whisper API:** same idea, paid.

**Option C — local `faster-whisper`:** no API or cost, works offline. It's slower on CPU, so use the `small` or `base` model for demo footage.

Word-level timestamps are **mandatory**. Alignment, filler removal and captions all depend on them.

## 3. Cloudinary

- Upload raw footage and get a URL plus auto thumbnails.
- Can do on-the-fly transformations, though you'll mainly use FFmpeg.
- For the demo, a local `/media` folder served by FastAPI `StaticFiles` works fine. Abstract it behind `services/storage.py` so swapping is easy.

## 5. Pexels (optional)

For script lines with no matching footage (`status: "missing"` in alignment), search Pexels for B-roll using LLM-generated keywords.

## 6. YouTube Data API (optional)

Real analytics for Creator Intelligence. OAuth setup takes time, so **mock analytics data** unless you have a spare teammate.

---

## `.env.example`

```
MONGODB_URI=mongodb+srv://<user>:<pass>@cluster0.xxxxx.mongodb.net/creatorai
GEMINI_API_KEY=
GROQ_API_KEY=
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
STORAGE_BACKEND=local        # local | cloudinary
PEXELS_API_KEY=              # optional
JWT_SECRET=
```

## Cost & rate-limit safety

- Cache every LLM output in Mongo (`generated_content`, `clips`) and never regenerate on page reload.
- Pre-process your demo footage before judging so the live demo replays cached results, then run one live generation to prove it works.
- Keep a backup Gemini key and a local Whisper fallback in case a free tier rate-limits you mid-demo.