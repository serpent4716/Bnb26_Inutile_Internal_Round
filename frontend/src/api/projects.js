import client from './client'

export const listProjects = () => client.get('/projects').then((r) => r.data)
export const createProject = (body) => client.post('/projects', body).then((r) => r.data)
export const getProject = (id) => client.get(`/projects/${id}`).then((r) => r.data)
export const saveScript = (projectId, content) => client.post('/scripts', { project_id: projectId, content }).then((r) => r.data)
export const processProject = (id) => client.post(`/projects/${id}/process`).then((r) => r.data)
export const buildRoughCut = (id) => client.post(`/projects/${id}/rough-cut`).then((r) => r.data)
export const setBestTake = (alignmentId, lineIdx, takeIndex) =>
  client.patch(`/alignments/${alignmentId}/lines/${lineIdx}`, { best_take_index: takeIndex }).then((r) => r.data)
export const setStage = (id, stage) => client.patch(`/projects/${id}/stage`, { stage }).then((r) => r.data)
export const publishProject = (id) => client.post(`/projects/${id}/publish`).then((r) => r.data)
