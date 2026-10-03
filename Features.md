# Feature Implementation Specs

Each feature lists: goal → inputs/outputs → implementation → collections touched → acceptance criteria.

---

## F1. Asset Management

**Goal:** Central, auto-organized, searchable library of all creator media.

**Implementation**
1. `POST /assets/upload` (multipart) → save to storage → create `assets` doc with `ai.status="pending"`.
2. Run `ffprobe` → fill `metadata`.
3. For video: extract keyframes (`ffmpeg -vf fps=1/3`), send 5–10 to Gemini Vision with a prompt asking for JSON `{tags: [], description: ""}`.
4. For video/audio: trigger transcription (F3 pipeline).
5. Chunk transcript (~30s windows) + description → embeddings → `embeddings` collection.
6. **Search:** `GET /assets/search?q=` → embed query → Atlas `$vectorSearch` → return asset + timestamp, so the user clicks and jumps to that moment.

**UI:** Grid with thumbnails, type filters, tag chips, a search bar and drag-and-drop upload.

**Acceptance:** Uploading a video produces tags plus a transcript, and searching a spoken phrase returns that video at the right timestamp.

---

## F2. AI Script & Hook Generation

**Goal:** Generate scripts, hooks and supporting content in the creator's voice.

**Implementation**
- `POST /generate/script` `{ idea, platform, duration, tone }` → returns script split into `lines` with sections (hook/intro/body/cta).
- `POST /generate/hooks` `{ project_id | clip_id, count: 5 }` → returns hook variants labeled by type: *question, bold claim, story, statistic, contrarian*.
- `POST /generate/supporting` `{ clip_id, platform }` → title, caption, hashtags, description, thumbnail text.
- **Tone personalization:** on first use, summarize 2–3 past scripts into `users.tone_profile` and inject it into every prompt.

**Prompt pattern (hooks)**
```
You are a short-form content strategist for a {niche} creator.
Creator tone: {tone_profile}
Clip transcript: {text}
Write 5 hooks (under 12 words each), one per type: question, bold_claim,
story, statistic, contrarian. Score each 1-10 for scroll-stopping power.
Return JSON: [{type, text, score}]
```

**Acceptance:** One click gives 5 distinct hook variants, and the creator can select or edit one, saved with `selected: true`.

---

## F3. Script-to-Video Understanding ⭐

**Goal:** Map every script line to where (and how well) it was spoken in the footage, handling retakes and ad-libs.

**Inputs:** `scripts.lines`, `transcripts.segments` (word timestamps)
**Output:** `alignments` document

**Algorithm**
1. **Normalize** text in both (lowercase, strip punctuation, expand numbers).
2. **Candidate matching:** for each script line, slide a window over transcript words of roughly the line length (±30%). Score with:
   - `rapidfuzz.fuzz.token_set_ratio` (fast lexical), and
   - embedding cosine similarity (semantic; catches paraphrases).
   - `similarity = 0.6 * lexical + 0.4 * semantic`
3. Keep all windows above a threshold (e.g. 0.75), since **multiple hits = retakes**.
4. **Pick best take:** highest similarity; tie-break on fewer filler words, fewer stumbles (repeated words), and being the *later* take (creators usually redo until it's right).
5. **Enforce order:** script lines should appear roughly in sequence. Use a simple dynamic-programming pass (like sequence alignment) so line 5 can't match before line 4 unless similarity is very high.
6. Transcript ranges matching no line → `unscripted_ranges` (ad-libs, often the best clip material).
7. Lines with no match → `status: "missing"` → suggest B-roll or re-record.
8. `coverage = matched / total lines`.

**Visual understanding (bonus):** attach the vision description of the keyframe nearest each matched range, so the UI shows "Line 4 → 03:12, *speaker at desk holding phone*".

**Rough cut from alignment:** best takes concatenated in script order become an automatic **rough-cut EDL** of the full video. That's a strong demo feature.

**UI:** Split view with script lines on the left, each showing a colored status (matched/retake/missing) and a timestamp. Clicking a line jumps the video there, and a dropdown switches takes.

**Acceptance:** On footage with deliberate retakes, the system picks the clean take, and missing lines are flagged.

---

## F4. Automated Clip Generation

**Goal:** Find the best 15–60s self-contained moments in long footage.

**Implementation**
1. Feed the LLM a **timestamped transcript** (segment-level: `[03:12-03:20] text`), chunked if long.
2. Prompt for candidate clips with `start`, `end`, `title`, `reason` and scores (hook strength, completeness, virality, 1–10).
3. **Post-process (important):**
   - Snap `start` and `end` to word boundaries using word timestamps, and never cut mid-word.
   - Extend to sentence ends and pad 0.15s.
   - Drop overlaps (keep the higher score) and enforce duration limits per platform.
4. Optional signal boost: audio energy peaks (laughter, emphasis) via `pydub` RMS add to the score.
5. Each candidate becomes a `clips` doc with an initial EDL (F5) and `status: "suggested"`.

**Prompt rules to include:** clip must make sense without context, start with a strong line (or flag that a hook overlay is needed), end on a resolution/punchline, and prefer stories, strong opinions, surprising facts and actionable tips.

**Acceptance:** A 10+ minute video yields 3–5 ranked clips that start and end cleanly.

---

## F5. AI-Assisted Editing (Editable)

**Goal:** AI applies edits, and the creator can change every one of them.

**Auto edits generated into the EDL**
| Edit | How |
|---|---|
| Silence removal | Gaps > 0.5s between words → split into segments |
| Filler removal | Words in filler list ("um", "uh", "like", "you know", "basically") → cut out |
| Retake removal | From alignment: drop non-best takes |
| Captions | Group words into 2–4 word chunks with timestamps; emphasize keywords (LLM-picked) |
| Zoom punches | Zoom 1.15–1.25x on emphasized sentences |
| Hook overlay | Selected hook as text in the first 2s |
| Smart crop | `crop_track` from face tracking (F6) |

**Editing UI (`ClipEditor.jsx`)**
- Timeline with segment blocks that support trim handles, delete and restore.
- A transcript panel where **deleting words deletes video** (Descript-style), which is a high-impact demo feature and easy to build on top of the EDL.
- Inline-editable caption track, plus toggles for zoom and crop.
- Preview: `<video>` with `timeupdate` listener that skips to the next segment's start when the current one ends, and captions rendered as positioned HTML.
- Every save pushes to `edl_versions` (`edited_by: "user"`) for undo/redo.

**Render:** `POST /clips/{id}/render` → FFmpeg:
- `trim` + `concat` filters for segments
- `crop` (dynamic via crop_track, or per-segment static crop as a simpler option)
- `zoompan`/`scale` for zooms
- captions → generate `.ass` subtitle file → `subtitles=` filter (supports bold, colors and positioning)

**Acceptance:** The user deletes a word in the transcript, the preview updates instantly, and the exported MP4 reflects it.

---

## F6. Multi-Platform Adaptation

**Goal:** One clip, many platform-ready versions.

**Platform presets**
```python
PLATFORMS = {
  "shorts":   {"aspect": "9:16", "max_dur": 60,  "captions": True,  "caption_style": "bold_center"},
  "reels":    {"aspect": "9:16", "max_dur": 90,  "captions": True,  "caption_style": "bold_center"},
  "tiktok":   {"aspect": "9:16", "max_dur": 180, "captions": True,  "caption_style": "bold_center"},
  "youtube":  {"aspect": "16:9", "max_dur": None,"captions": False},
  "linkedin": {"aspect": "1:1",  "max_dur": 600, "captions": True,  "caption_style": "clean_bottom"},
  "x":        {"aspect": "16:9", "max_dur": 140, "captions": True},
}
```

**Smart reframe (16:9 → 9:16)**
1. Sample frames at ~5 fps, run MediaPipe Face Detection, and get the face center x.
2. Smooth the x positions (moving average or EMA) to avoid jitter → `crop_track`.
3. No face → center crop.
4. Crop width = `height * 9/16`.

**Copy adaptation:** the LLM rewrites caption, title and hashtags per platform (LinkedIn is professional, Reels is casual with emojis, X is short).

**Acceptance:** A single click on "Adapt for all" gives a 9:16 version with tracked crop, plus per-platform copy.

---

## F7. Content Workflow

**Goal:** Track each content piece from idea to published.

**Implementation**
- Kanban board over `projects.stage` with drag and drop (`@dnd-kit/core`).
- Every stage change is appended to `stage_history` (powers F8 production insights).
- **Auto-advance:** script saved → `scripting` done; footage uploaded → `editing`; clip approved → `review`; export → `scheduled` or `published`.
- A calendar view for `scheduled_for` (optional).
- An **"Idea" capture** form where the AI expands an idea into 3 angles and a title.
- Publishing can be mocked: a "Publish" button that marks the project published and creates a mock `analytics` doc.

**Acceptance:** Cards move through stages and the project detail page shows script, footage, clips and copy in one place.

---

## F8. Creator Intelligence

**Goal:** Insights on performance and production.

**Performance insights** (from `analytics`, seeded with realistic mock data)
- Views and retention by hook type, platform and topic
- Best posting days and times
- Top clips leaderboard

**Production insights** (from real `stage_history` + `jobs`)
- Average time per stage, showing where the bottleneck is
- Posting frequency trend
- Time saved by AI: (raw footage minutes − final minutes) and an estimate of manual editing time

**AI insight cards:** send aggregated stats (not raw data) to the LLM → 3–5 actionable insights in plain language, e.g. *"Question hooks average 2.1x the 3-second retention of statement hooks. Your next 3 scripts start with questions."*

**UI:** Recharts dashboard plus insight cards.

**Acceptance:** The dashboard renders charts and AI-written insights that reference real numbers from the data.