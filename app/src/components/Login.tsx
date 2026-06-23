import { useState, type FormEvent } from 'react'
import StarsBackground from './StarsBackground'
import { HoverReveal } from './HoverReveal'

interface LoginProps {
  onAuth: () => void
}

export default function Login({ onAuth }: LoginProps) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (res.ok) {
        onAuth()
      } else {
        setError('Incorrect password')
        setPassword('')
      }
    } catch {
      setError('Connection error — please retry')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ position: 'relative', minHeight: '100vh', overflow: 'hidden', background: '#080c14' }}>

      {/* Aurora background */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 0 }}>
        <StarsBackground />
      </div>

      {/* Content */}
      <div style={{
        position: 'relative',
        zIndex: 10,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        gap: 32,
        fontFamily: 'var(--font-sans, system-ui, sans-serif)',
      }}>

        {/* Hover-reveal branding */}
        <div style={{ textAlign: 'center' }}>
          <HoverReveal
            items={['H', 'E', 'R', 'M', 'E', 'S']}
            className="text-7xl font-black"
          />
          <p style={{ fontSize: 11, color: '#6a7088', marginTop: 6, letterSpacing: '0.25em' }}>
            TASK DISPATCHER
          </p>
        </div>

        {/* Auth form */}
        <form
          onSubmit={handleSubmit}
          style={{
            width: 380,
            background: 'linear-gradient(180deg, #0d121d, #090d15)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 16,
            padding: '40px 36px',
            boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
          }}
        >
          {/* Heading */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 18, fontWeight: 600, color: '#e8eaf2', marginBottom: 4 }}>
              Sign in
            </div>
            <div style={{ fontSize: 13, color: '#565d72' }}>Enter your password to continue</div>
          </div>

          {/* Password field */}
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Enter password"
            disabled={loading}
            autoFocus
            style={{
              display: 'block',
              width: '100%',
              boxSizing: 'border-box',
              padding: '11px 14px',
              background: 'rgba(255,255,255,0.04)',
              border: error ? '1px solid rgba(239,68,68,0.5)' : '1px solid rgba(255,255,255,0.09)',
              borderRadius: 9,
              color: '#e8eaf2',
              fontSize: 14,
              outline: 'none',
              marginBottom: 12,
              transition: 'border-color 0.15s',
            }}
          />

          {/* Error */}
          {error && (
            <div
              style={{
                fontSize: 12,
                color: '#f87171',
                marginBottom: 16,
                padding: '8px 12px',
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.18)',
                borderRadius: 7,
              }}
            >
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading || !password}
            style={{
              display: 'block',
              width: '100%',
              padding: '11px 14px',
              background: loading || !password ? 'rgba(246,183,60,0.3)' : '#f6b73c',
              color: loading || !password ? 'rgba(255,255,255,0.4)' : '#0d0a00',
              border: 'none',
              borderRadius: 9,
              fontSize: 14,
              fontWeight: 600,
              cursor: loading || !password ? 'not-allowed' : 'pointer',
              transition: 'background 0.15s, color 0.15s',
              marginTop: error ? 0 : 4,
            }}
          >
            {loading ? 'Verifying…' : 'Unlock'}
          </button>
        </form>
      </div>
    </div>
  )
}
