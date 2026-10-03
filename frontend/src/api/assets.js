import client from './client'

export const listAssets = (params) => client.get('/assets', { params }).then((r) => r.data)
export const getAsset = (id) => client.get(`/assets/${id}`).then((r) => r.data)
export const getTranscript = (id) => client.get(`/assets/${id}/transcript`).then((r) => r.data)
export const getJob = (id) => client.get(`/jobs/${id}`).then((r) => r.data)

export function uploadAsset(file, onProgress, projectId) {
  const form = new FormData()
  form.append('file', file)
  if (projectId) form.append('project_id', projectId)
  return client
    .post('/assets/upload', form, { onUploadProgress: (e) => e.total && onProgress?.(e.loaded / e.total) })
    .then((r) => r.data)
}

/** Poll a job until it finishes. Resolves with the job, rejects with its error. */
export async function waitForJob(id, onTick) {
  for (;;) {
    const job = await getJob(id)
    onTick?.(job)
    if (job.status === 'done') return job
    if (job.status === 'failed') throw new Error(job.error || 'Job failed')
    await new Promise((r) => setTimeout(r, 1500))
  }
}
export const searchAssets = (q) => client.get('/assets/search', { params: { q } }).then((r) => r.data)
export const listJobs = (active) => client.get('/jobs', { params: { active } }).then((r) => r.data)
