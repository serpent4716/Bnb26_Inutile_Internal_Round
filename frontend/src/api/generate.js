import client from './client'

export const generateHooks = (clipId) => client.post('/generate/hooks', { clip_id: clipId, count: 5 }).then((r) => r.data)
export const listGenerated = (params) => client.get('/generated', { params }).then((r) => r.data)
export const selectVariant = (id, variantIndex, text) =>
  client.patch(`/generated/${id}/select`, { variant_index: variantIndex, ...(text ? { text } : {}) }).then((r) => r.data)
