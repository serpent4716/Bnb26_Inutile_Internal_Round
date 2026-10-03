import client from './client'
import { useAuth } from '../store/auth'

const T = '/t2s'
const data = (r) => r.data

export const getConfig = () => client.get(`${T}/config`).then(data)
export const getTrends = (region, category, refresh) =>
  client.get(`${T}/trends`, { params: { region, category: category || undefined, refresh: refresh || undefined } }).then(data)
export const listRuns = () => client.get(`${T}/runs`).then(data)
export const createRun = (trendId, mode) => client.post(`${T}/runs`, { trend_id: trendId, mode }).then(data)
export const getRun = (id) => client.get(`${T}/runs/${id}`).then(data)
export const getRunLog = (id) => client.get(`${T}/runs/${id}/log`).then(data)
export const approveRun = (id) => client.post(`${T}/runs/${id}/approve`).then(data)
export const setRunMode = (id, mode) => client.post(`${T}/runs/${id}/mode`, { mode }).then(data)
export const patchScript = (id, script) => client.patch(`${T}/runs/${id}/script`, { script }).then(data)
export const patchEdl = (id, edl) => client.patch(`${T}/runs/${id}/edl`, edl).then(data)
export const swapVisual = (id, sceneId, candidateIndex) =>
  client.patch(`${T}/runs/${id}/visuals`, { scene_id: sceneId, candidate_index: candidateIndex }).then(data)
export const rerunStage = (id, stage) => client.post(`${T}/runs/${id}/stages/${stage}/rerun`).then(data)
export const publishRun = (id, body) => client.post(`${T}/runs/${id}/publish`, body).then(data)
export const saveToCreatorAi = (id) => client.post(`${T}/runs/${id}/save`).then(data)
export const getProviders = () => client.get(`${T}/health/providers`).then(data)

/** EventSource can't send an Authorization header, so the stream takes the token as a query param. */
export const runEventsUrl = (id) =>
  `${client.defaults.baseURL}${T}/runs/${id}/events?token=${encodeURIComponent(useAuth.getState().token ?? '')}`

/** Generated files are served by the backend (path-restricted); remote previews are used directly. */
export const fileUrl = (p) =>
  !p ? '' : /^https?:/.test(p) ? p : `${client.defaults.baseURL}${T}/files?path=${encodeURIComponent(p)}`

const PROVIDER_LABEL = {
  gemini: 'Gemini', groq: 'Groq', openrouter: 'OpenRouter', ollama: 'Ollama', mock: 'Mock',
  edge: 'edge-tts', piper: 'Piper', kokoro: 'Kokoro', estimate: 'estimated timings',
  pexels: 'Pexels', pixabay: 'Pixabay', 'pexels-photo': 'Pexels stills', 'pixabay-photo': 'Pixabay stills',
  demo: 'demo assets', ffmpeg: 'FFmpeg', 'user-edit': 'your edit', 'disk-cache': 'cache',
  heuristic: 'heuristic', 'single-candidate': 'only option', 'dry-run': 'dry run',
}
export const providerLabel = (p) => PROVIDER_LABEL[p] || (p?.startsWith('faster-whisper') ? 'faster-whisper' : p)

export const STAGE_NAMES = { script: 'Script', audio: 'Voiceover', visuals: 'Footage', assembly: 'Video', publish: 'Publish' }
export const STATE_TEXT = {
  trend_selected: 'Starting', scripting: 'Writing the script', voicing: 'Recording the voiceover',
  sourcing_visuals: 'Finding footage', assembling: 'Rendering the video', ready_for_review: 'Ready for review',
  publishing: 'Publishing', published: 'Published', failed: 'Stopped',
}
