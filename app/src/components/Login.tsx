import { useState, type FormEvent } from 'react'

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
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: '#080c14',
        fontFamily: 'var(--font-sans, system-ui, sans-serif)',
      }}
    >
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
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 36 }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 38,
              height: 38,
              borderRadius: 11,
              background: 'linear-gradient(135deg, #f6b73c, #c2410c)',
              boxShadow: '0 0 22px rgba(246,183,60,0.35), 0 4px 16px rgba(0,0,0,0.5)',
              flexShrink: 0,
            }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M9 1L16 5V13L9 17L2 13V5L9 1Z" stroke="#fff" strokeWidth="1.5" fill="none" />
              <path d="M9 5L13 7.5V12.5L9 15L5 12.5V7.5L9 5Z" fill="rgba(255,255,255,0.2)" stroke="#fff" strokeWidth="1" />
            </svg>
          </span>
          <div style={{ lineHeight: 1.2 }}>
            <div
              style={{
                fontFamily: 'var(--font-display, monospace)',
                fontWeight: 700,
                fontSize: 14,
                letterSpacing: '0.06em',
                color: '#f0f2f8',
              }}
            >
              HERMES
            </div>
            <div style={{ fontSize: 11, color: '#6a7088', marginTop: 1 }}>Task Dispatcher</div>
          </div>
        </div>

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
  )
}
