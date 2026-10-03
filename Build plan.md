# Build Plan

## Priority tiers

| Tier | Features | Why |
|---|---|---|
| **P0: must work live** | F3 Script-to-Video alignment, F4 Clip generation, F5 Editable EDL + preview + render | This is the PS's core loop, and judges will test it |
| **P1: high demo value** | F2 Hooks/captions, F6 9:16 smart reframe, transcript-based editing | Visible, impressive, fairly quick |
| **P2: present but lighter** | F1 Library + semantic search, F7 Kanban, F8 Insights (mock analytics) | Shows full "operating platform" vision |

## Team split (4 people)

| Role | Owns |
|---|---|
| **A: AI/Pipeline lead** | Transcription, alignment algorithm, clip finder, LLM prompts |
| **B: Media engineer** | FFmpeg rendering, silence/filler cuts, captions (.ass), MediaPipe reframe |
| **C: Backend** | FastAPI routes, MongoDB models, jobs, storage, auth, vector search |
| **D: Frontend** | Timeline editor, video preview, library, kanban, insights dashboard |

With 3 people, merge B into A and C. With 2, cut F8 down to a static mock and F1 search down to a text index.

## Timeline (adjust to your hackathon length)

### Phase 0: Setup (first ~2 hrs)
- [ ] Repo, folder structure (see ARCHITECTURE.md), `.env`
- [ ] MongoDB Atlas cluster, Gemini + Groq keys tested
- [ ] FFmpeg installed on all machines
- [ ] **Record demo footage now**: 5–10 min talking video following a script, with 2–3 deliberate retakes, some "umm"s and one ad-lib story
- [ ] Agree on the EDL JSON format (everyone builds against it)

### Phase 1: Core pipeline (P0)
- [ ] Upload → storage → ffprobe → `assets`
- [ ] Audio extraction → Whisper → `transcripts` with words
- [ ] Alignment service + alignment UI
- [ ] Clip finder → `clips` with initial EDL
- [ ] Silence + filler removal in EDL
- [ ] Frontend EDL preview player
- [ ] FFmpeg render of EDL (16:9 first)
- **Checkpoint:** script + footage in → clips out → playable MP4

### Phase 2: Polish the loop (P1)
- [ ] Captions (word-chunked) in preview + burned into render
- [ ] Timeline editor: trim, delete, restore segments
- [ ] Transcript-based editing (delete word → cut)
- [ ] Face-tracked 9:16 reframe
- [ ] Hook + caption + hashtag generation per platform
- [ ] EDL versioning / undo
- **Checkpoint:** full demo flow works end to end

### Phase 3: Platform breadth (P2)
- [ ] Asset library grid + auto tags + semantic search
- [ ] Kanban workflow with auto stage changes
- [ ] Insights dashboard with seeded analytics + AI insight cards
- [ ] Script generator from idea

### Phase 4: Demo prep (last ~3 hrs, don't skip)
- [ ] Pre-process demo footage, cache everything
- [ ] Fallbacks: local Whisper, backup API key, pre-rendered MP4s
- [ ] Pitch deck: problem → solution → live demo → architecture → impact
- [ ] Rehearse the demo 3 times with a timer

## Demo script (~4 min)

1. **Problem (30s):** "A creator uses 6+ tools. Here's one."
2. **Upload (20s):** Drop script + raw footage. Show the pipeline progress steps.
3. **Script understanding (40s):** Alignment view showing lines matched, retakes detected and the clean take auto-selected, plus a flagged missing line. Click a line to jump to the moment.
4. **Clips (40s):** 4 ranked clips with AI reasons and scores. Play the top one in 9:16 with captions and face tracking.
5. **Creator control (40s):** Open the editor, delete a word in the transcript, trim a segment, swap the hook. Re-render.
6. **Adapt (30s):** "Adapt for all" produces Shorts, Reels and LinkedIn versions with per-platform captions.
7. **Platform (30s):** Kanban card moved to Published, library search finds a spoken phrase, insights dashboard.
8. **Close (10s):** Time saved metric. "30 minutes of footage → 5 posts in 3 minutes."

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Rendering is slow | Render only on export, use `-preset ultrafast`, keep demo clips short |
| API rate limits | Cache all outputs, keep a backup key and a local Whisper fallback |
| Bad clip boundaries | Always snap to word timestamps and sentence ends |
| Jittery crop | Smooth crop_track, or fall back to per-segment static crops |
| Scope creep | Finish the P0 checkpoint before touching P2 |