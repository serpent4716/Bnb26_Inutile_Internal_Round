# Backend API Endpoints (FastAPI)

Base URL: `/api/v1`. All routes except auth require `Authorization: Bearer <jwt>`.

## Auth
| Method | Route | Body / Notes |
|---|---|---|
| POST | `/auth/register` | `{name, email, password, niche}` |
| POST | `/auth/login` | `{email, password}` → `{token}` |
| GET | `/auth/me` | current user |

## Assets (F1)
| Method | Route | Notes |
|---|---|---|
| POST | `/assets/upload` | multipart `file`, optional `project_id` → `{asset, job_id}`; video/audio start a transcription job |
| GET | `/assets` | `?type=&project_id=&tag=` |
| GET | `/assets/{id}` | includes `ai` block |
| DELETE | `/assets/{id}` | |
| GET | `/assets/search` | `?q=` semantic search (Atlas Vector Search, text-index fallback) → `[{asset, start, end, snippet, score, kind, match}]` |
| GET | `/assets/{id}/transcript` | |

## Projects / Workflow (F7)
| Method | Route | Notes |
|---|---|---|
| POST | `/projects` | `{title, idea, target_platforms}` |
| GET | `/projects` | `?stage=` |
| GET | `/projects/{id}` | populated: script, assets, clips, alignment |
| PATCH | `/projects/{id}` | update fields |
| PATCH | `/projects/{id}/stage` | `{stage}` → appends `stage_history` |
| POST | `/projects/{id}/publish` | MOCK publish: stage → published + mock analytics per ready clip × platform |

## Scripts & Generation (F2)
| Method | Route | Notes |
|---|---|---|
| POST | `/scripts` | `{project_id, content}` → parses into lines |
| PUT | `/scripts/{id}` | new version |
| POST | `/generate/script` | `{idea, platform, duration, tone}` |
| POST | `/generate/hooks` | `{project_id?, clip_id?, count}` |
| POST | `/generate/supporting` | `{clip_id, platform}` → title/caption/hashtags/description |
| POST | `/generate/ideas` | `{idea}` → angles + titles |
| POST | `/generate/tone-profile` | rebuild `users.tone_profile` from the latest scripts |
| GET | `/generated` | `?clip_id=&project_id=&type=&platform=` |
| PATCH | `/generated/{id}/select` | `{variant_index, text?}`; a selected hook becomes the clip's 0-2s overlay |

## Processing Pipeline (F3, F4)
| Method | Route | Notes |
|---|---|---|
| POST | `/projects/{id}/process` | runs full pipeline → `{job_id}` |
| GET | `/jobs` | `?active=true` → queued/running jobs (dashboard) |
| GET | `/jobs/{id}` | `{status, current_step, progress, error}` |
| GET | `/projects/{id}/alignment` | alignment doc |
| PATCH | `/alignments/{id}/lines/{idx}` | `{best_take_index}`, user picks a different take |
| POST | `/projects/{id}/rough-cut` | builds full-video EDL from best takes |

## Clips & Editing (F4, F5, F6)
| Method | Route | Notes |
|---|---|---|
| GET | `/projects/{id}/clips` | sorted by score |
| GET | `/clips/{id}` | |
| PUT | `/clips/{id}/edl` | save edited EDL (pushes version, `edited_by: user`) |
| POST | `/clips/{id}/undo` | revert to previous EDL version |
| PATCH | `/clips/{id}/status` | `{status}`: `approved` / `rejected` / `suggested` (undo a decision) |
| POST | `/clips/{id}/adapt` | `{platforms?}` (default all) → `{job_id}`; face-tracked crop, per-platform EDL variants + copy |
| POST | `/clips/{id}/render` | `{platform?}` → `{job_id}`; result in `clip.render.url` or that variant's `render.url` |

## Insights (F8)
| Method | Route | Notes |
|---|---|---|
| GET | `/insights/performance` | aggregated chart data |
| GET | `/insights/production` | stage timings, frequency, time saved |
| POST | `/insights/ai-summary` | LLM insight cards; cached as generated_content `type: insights` (read with `GET /generated?type=insights`) |
| POST | `/dev/seed-analytics` | seed mock data (dev only, `ENABLE_DEV_ENDPOINTS`) |
| POST | `/dev/reindex-embeddings` | build search embeddings for already-transcribed assets (dev only) |

## Error format
```json
{ "detail": "Human readable message", "code": "TRANSCRIPTION_FAILED" }
```