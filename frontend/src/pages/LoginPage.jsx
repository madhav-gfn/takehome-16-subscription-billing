import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ErrorBanner, Spinner } from '../components/common'

const DEMO = [
  { role: 'Billing admin', email: 'admin@example.com', password: 'admin123' },
  { role: 'Account manager', email: 'manager1@example.com', password: 'manager123' },
  { role: 'Account manager', email: 'manager2@example.com', password: 'manager123' },
]

export default function LoginPage() {
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  if (loading) return <Spinner />
  if (user) return <Navigate to="/" replace />

  async function submit(e) {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <h1>Subscription Billing</h1>
        <p className="subtle" style={{ marginBottom: 24 }}>Sign in to continue</p>

        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email" type="email" value={email} autoComplete="username"
              onChange={(e) => setEmail(e.target.value)} required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password" type="password" value={password} autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)} required
            />
          </div>
          <button className="primary" type="submit" disabled={pending} style={{ width: '100%' }}>
            {pending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        {/* A reviewer opening the live URL should be one click from each role. */}
        <div className="demo-creds">
          <p className="subtle" style={{ marginBottom: 8 }}>Demo accounts — click to fill</p>
          {DEMO.map((d) => (
            <button
              key={d.email} type="button"
              onClick={() => { setEmail(d.email); setPassword(d.password) }}
            >
              <strong>{d.role}</strong> — {d.email}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
