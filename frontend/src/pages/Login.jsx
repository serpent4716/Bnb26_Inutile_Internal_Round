import { useState } from 'react'
import { login, register } from '../api/auth'
import { errorMessage } from '../api/client'
import { useAuth } from '../store/auth'
import { btn, errorText, field } from '../components/ui'
import { Wordmark } from '../App'

function Field({ label, hint, ...props }) {
  return (
    <label className="grid gap-2 text-sm font-semibold">
      {label}
      <input className={field} {...props} />
      {hint && <span className="text-sm font-normal text-mute">{hint}</span>}
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
    <div className="grid min-h-[100dvh] lg:grid-cols-[1.15fr_1fr]">
      {/* hero-band: the one full-bleed orange surface, with the atmospheric mesh */}
      <section
        className="relative flex flex-col justify-between overflow-hidden bg-primary px-6 py-10 text-on-dark md:px-12 md:py-14"
        style={{ backgroundImage: 'radial-gradient(120% 90% at 85% 15%, var(--color-hero-glow) 0%, transparent 55%), radial-gradient(90% 70% at 10% 110%, var(--color-hero-pink) 0%, transparent 60%)' }}
      >
        <Wordmark className="text-on-dark" cut="border-l-primary" />
        <div className="mt-16 lg:mt-0">
          <h1 className="font-display text-[clamp(3rem,7vw+1rem,8rem)] leading-none font-bold tracking-[-0.03em]">
            Footage in.<br />Posts out.
          </h1>
          <p className="mt-6 max-w-[34ch] text-lg leading-relaxed font-semibold text-on-dark-mute">
            Your script and raw take become ranked, captioned, platform-ready clips you can still edit.
          </p>
        </div>
      </section>

      <section className="flex items-center px-6 py-12 md:px-12">
        <form onSubmit={submit} className="mx-auto grid w-full max-w-sm gap-5">
          <h2 className="display-md">{mode === 'login' ? 'Sign in' : 'Create your account'}</h2>
          {mode === 'register' && <Field label="Name" value={form.name} onChange={set('name')} required autoComplete="name" />}
          <Field label="Email" type="email" value={form.email} onChange={set('email')} required autoComplete="email" />
          <Field
            label="Password" type="password" value={form.password} onChange={set('password')} required
            minLength={mode === 'register' ? 8 : undefined} autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            hint={mode === 'register' ? 'At least 8 characters.' : undefined}
          />
          {mode === 'register' && (
            <Field label="Niche" value={form.niche} onChange={set('niche')} placeholder="Personal finance, tech, fitness" hint="Optional. Used to tune hooks and copy." />
          )}
          {error && <p role="alert" className={errorText}>{error}</p>}
          {/* the orange hero is this view's stamp, so the submit is the dark CTA */}
          <button disabled={busy} className={`${btn.dark} w-full`}>
            {busy ? 'One moment' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
          <button
            type="button"
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
            className="justify-self-center rounded-full px-2 text-sm font-semibold text-charcoal hover:text-ink focus-ring"
          >
            {mode === 'login' ? 'New here? Create an account' : 'Have an account? Sign in'}
          </button>
        </form>
      </section>
    </div>
  )
}
