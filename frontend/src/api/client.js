import axios from 'axios'
import { useAuth } from '../store/auth'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1',
})

client.interceptors.request.use((config) => {
  const { token } = useAuth.getState()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) useAuth.getState().logout()
    return Promise.reject(err)
  },
)

/** Local storage URLs are relative (/media/...); Cloudinary ones are absolute. */
export const mediaUrl = (url) => url && new URL(url, client.defaults.baseURL).href

export const errorMessage = (err, fallback = 'Something went wrong.') => err.response?.data?.detail ?? fallback

export default client
