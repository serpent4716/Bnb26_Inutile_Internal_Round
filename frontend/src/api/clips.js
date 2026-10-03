import client from './client'

export const getClip = (id) => client.get(`/clips/${id}`).then((r) => r.data)
export const setClipStatus = (id, status) => client.patch(`/clips/${id}/status`, { status }).then((r) => r.data)
export const adaptClip = (id, platforms) => client.post(`/clips/${id}/adapt`, platforms ? { platforms } : {}).then((r) => r.data)
export const renderClip = (id, platform) => client.post(`/clips/${id}/render`, { platform }).then((r) => r.data)
