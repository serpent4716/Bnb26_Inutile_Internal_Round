# Database Schema — MongoDB

## Why MongoDB fits

- **EDLs, transcripts and AI outputs are nested JSON**, which maps naturally to documents. SQL would need many join tables.
- **Flexible schema** lets you add fields mid-hackathon without migrations.
- **Atlas Vector Search** handles semantic asset search ("clip where I talk about budgeting") inside the same database, so you don't need Pinecone.
- The free M0 cluster is enough for a demo.

Driver: **Motor** (async) with FastAPI, and Pydantic models for validation.

---

## Collections

### 1. `users`
```js
{
  _id: ObjectId,
  name: String,
  email: String,            // unique
  password_hash: String,
  niche: String,            // "personal finance", "tech" — used in prompts
  tone_profile: String,     // AI-generated summary of creator's style
  connected_platforms: [String],  // ["youtube", "instagram"]
  created_at: Date
}
```

### 2. `projects` (a piece of content moving through the workflow)
```js
{
  _id: ObjectId,
  user_id: ObjectId,
  title: String,
  idea: String,
  stage: String,            // "idea" | "scripting" | "recording" | "editing"
                            // | "review" | "scheduled" | "published"
  stage_history: [ { stage: String, at: Date } ],   // powers production insights
  script_id: ObjectId,
  footage_asset_ids: [ObjectId],
  target_platforms: [String],
  scheduled_for: Date,
  published_at: Date,
  tags: [String],
  created_at: Date,
  updated_at: Date
}
```
Indexes: `{ user_id: 1, stage: 1 }`, `{ user_id: 1, updated_at: -1 }`

### 3. `assets`
```js
{
  _id: ObjectId,
  user_id: ObjectId,
  project_id: ObjectId,      // optional
  type: String,              // "video" | "image" | "audio" | "document"
  filename: String,
  storage_url: String,
  thumbnail_url: String,
  mime_type: String,
  size_bytes: Number,
  metadata: {                // from ffprobe
    duration: Number, width: Number, height: Number, fps: Number
  },
  ai: {
    tags: [String],          // ["talking head", "outdoor", "laptop"]
    description: String,     // scene summary from vision model
    transcript_id: ObjectId,
    keyframes: [ { t: Number, description: String } ],  // vision descriptions of sampled keyframes
    status: String           // "pending" | "processing" | "ready" | "failed"
  },
  created_at: Date
}
```
Indexes: `{ user_id: 1, type: 1 }`, text index on `filename, ai.tags, ai.description`

### 4. `transcripts`
```js
{
  _id: ObjectId,
  asset_id: ObjectId,
  language: String,
  full_text: String,
  segments: [
    {
      idx: Number,
      start: Number, end: Number,
      text: String,
      words: [ { w: String, start: Number, end: Number, conf: Number } ],
      is_filler: Boolean,
      silence_after: Number   // seconds of silence after this segment
    }
  ],
  created_at: Date
}
```
Large transcripts are fine, since MongoDB's document limit is 16MB, which is roughly hours of words.

### 5. `scripts`
```js
{
  _id: ObjectId,
  user_id: ObjectId,
  project_id: ObjectId,
  title: String,
  content: String,
  lines: [ { idx: Number, text: String, section: String } ],  // "hook" | "intro" | "body" | "cta"
  source: String,            // "user" | "ai_generated"
  version: Number,
  created_at: Date
}
```

### 6. `alignments` (script ↔ footage mapping)
```js
{
  _id: ObjectId,
  project_id: ObjectId,
  script_id: ObjectId,
  asset_id: ObjectId,
  matches: [
    {
      script_line_idx: Number,
      takes: [
        { start: Number, end: Number, similarity: Number, transcript_segment_idxs: [Number],
          visual: String }   // nearest keyframe's description
      ],
      best_take_index: Number,
      status: String          // "matched" | "missing" | "ad_libbed"
    }
  ],
  unscripted_ranges: [ { start: Number, end: Number, text: String } ],
  coverage: Number,           // fraction (0-1) of script lines found in footage
  created_at: Date
}
```

### 7. `clips` (holds the editable EDL)
```js
{
  _id: ObjectId,
  project_id: ObjectId,
  source_asset_id: ObjectId,
  kind: String,               // "short" | "rough_cut" (one rough cut per project)
  title: String,
  reason: String,             // why AI picked it
  scores: { hook: Number, completeness: Number, virality: Number, overall: Number },
  edl: {                      // segments in source seconds; captions/zooms/overlays/crop_track in clip-timeline seconds
    aspect_ratio: String,     // "16:9" | "9:16" | "1:1"
    caption_style: String,    // "bold_center" | "clean_bottom"
    segments: [ { start: Number, end: Number } ],
    captions: [ { start: Number, end: Number, text: String, style: String } ],
    zooms: [ { start: Number, end: Number, scale: Number } ],
    crop_track: [ { t: Number, x_center: Number } ],
    overlays: [ { type: String, asset_id: ObjectId, text: String, start: Number, end: Number } ]  // type "hook": selected hook, first 2s
  },
  edl_versions: [ { edl: Object, edited_by: String, at: Date } ],  // "ai" | "user" — undo + shows creator control
  render: { status: String, url: String, rendered_at: Date },   // status: rendering | done | failed | stale
  variants: [ { platform: String, edl: Object, render: Object } ],   // F6 per-platform versions
  status: String,             // "suggested" | "approved" | "rejected" | "exported"
  created_at: Date
}
```
Index: `{ project_id: 1, "scores.overall": -1 }`

### 8. `generated_content` (hooks, captions, titles, etc.)
```js
{
  _id: ObjectId,
  user_id: ObjectId,
  project_id: ObjectId,
  clip_id: ObjectId,          // optional
  type: String,               // "hook" | "title" | "caption" | "hashtags" | "description" | "thumbnail_text" | "script" | "ideas"
  platform: String,           // "youtube" | "shorts" | "reels" | "tiktok" | "linkedin" | "x"
  variants: [ { text: String, selected: Boolean, score: Number, label: String } ],  // label: hook type / idea title
  prompt_context: String,
  created_at: Date
}
```

### 9. `embeddings` (for semantic search via Atlas Vector Search)
```js
{
  _id: ObjectId,
  user_id: ObjectId,
  asset_id: ObjectId,
  kind: String,               // "transcript_chunk" | "visual_description" | "script"
  text: String,
  start: Number, end: Number, // for transcript chunks → jump to timestamp
  vector: [Number]            // e.g. 768 dims (Gemini text-embedding)
}
```
Atlas Vector Search index `embeddings_vector` on `vector` (768 dims, cosine) with a filter on `user_id` - JSON in `backend/app/services/search.py`. Text index on `text` is the keyword fallback.

### 10. `jobs`
```js
{
  _id: ObjectId,
  user_id: ObjectId,          // owner, GET /jobs/{id} is scoped to it
  project_id: ObjectId,       // optional
  type: String,               // "pipeline" | "transcription" | "render" | "tagging" | "adapt"
  status: String,             // "queued" | "running" | "done" | "failed"
  current_step: String,       // "transcribing", "aligning", ...
  progress: Number,           // 0–100
  error: String,
  created_at: Date, finished_at: Date
}
```

### 11. `analytics` (performance data, real or mocked)
```js
{
  _id: ObjectId,
  user_id: ObjectId,
  project_id: ObjectId,
  clip_id: ObjectId,
  platform: String,
  posted_at: Date,
  metrics: { views: Number, likes: Number, comments: Number, shares: Number,
             watch_time_avg: Number, retention_3s: Number },
  hook_type: String,          // "question" | "bold_claim" | "story" — for insights
  title: String,              // post title (top-posts table)
  mock: Boolean,              // MOCK: seeded or mock-published, not from a real platform
  snapshot_at: Date
}
```

---

## Relationships at a glance

```
user ─┬─< projects ─┬── script
      │             ├─< assets ── transcript
      │             ├── alignment
      │             ├─< clips (EDL) ─< generated_content
      │             └─< jobs
      ├─< assets ─< embeddings
      └─< analytics
```