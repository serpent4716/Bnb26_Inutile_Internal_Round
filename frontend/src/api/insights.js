import client from './client'

export const getPerformance = () => client.get('/insights/performance').then((r) => r.data)
export const getProduction = () => client.get('/insights/production').then((r) => r.data)
export const generateInsights = () => client.post('/insights/ai-summary').then((r) => r.data)
export const latestInsights = () => client.get('/generated', { params: { type: 'insights' } }).then((r) => r.data[0] ?? null)
export const seedAnalytics = () => client.post('/dev/seed-analytics').then((r) => r.data) // MOCK data
