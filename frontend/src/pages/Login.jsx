import { useState } from 'react'
import { VideoCamera } from '@phosphor-icons/react'
import { login, register } from '../api/auth'
import { errorMessage } from '../api/client'
import { useAuth } from '../store/auth'

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-500 focus:border-orange-500 focus:outline-2 focus:outline-orange-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder:text-zinc-400'

function Field({ label, ...props }) {
  return (
    <label className="grid gap-2 text-sm font-medium">
      {label}
      <input className={input} {...props} />
    </label>
  )
}

export default function Login() {
  const setToken = useAuth((s) => s.setToken)
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '', niche: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { token } = mode === 'login' ? await login({ email: form.email, password: form.password }) : await register(form)
      setToken(token)
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(Array.isArray(detail) ? 'Check the fields above. Passwords need at least 8 characters.' : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-[100dvh] items-center px-4">
      <form onSubmit={submit} className="mx-auto grid w-full max-w-sm gap-5">
        <div className="flex items-center gap-2">
          <VideoCamera size={24} weight="fill" className="text-orange-500" />
          <span className="text-lg font-semibold tracking-tight">CreatorAi</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
        {mode === 'register' && <Field label="Name" value={form.name} onChange={set('name')} required autoComplete="name" />}
        <Field label="Email" type="email" value={form.email} onChange={set('email')} required autoComplete="email" />
        <Field label="Password" type="password" value={form.password} onChange={set('password')} required minLength={mode === 'register' ? 8 : undefined} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
        {mode === 'register' && <Field label="Niche (optional)" value={form.niche} onChange={set('niche')} placeholder="Personal finance, tech, fitness..." />}
        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button
          disabled={busy}
          className="rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-orange-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 active:scale-[0.98] disabled:opacity-60"
        >
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
        <button
          type="button"
          onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
          className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          {mode === 'login' ? 'New here? Create an account' : 'Have an account? Sign in'}
        </button>
      </form>
    </div>
  )
}
