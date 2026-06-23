import { useEffect, useState } from 'react'
import Shell from './components/Shell'
import Login from './components/Login'

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)

  useEffect(() => {
    fetch('/api/auth/check')
      .then(r => r.json())
      .then((data: { authenticated: boolean }) => setAuthed(data.authenticated))
      .catch(() => setAuthed(false))
  }, [])

  if (authed === null) {
    return <div style={{ height: '100vh', background: '#080c14' }} />
  }

  if (!authed) {
    return <Login onAuth={() => setAuthed(true)} />
  }

  return <Shell />
}
