import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { authApi } from '../api/resources'
import { tokens } from '../api/client'

const AuthContext = createContext(null)

export function useAuth() {
  return useContext(AuthContext)
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // `loading` matters: without it, a page refresh renders RequireAuth before
  // /me/ resolves and bounces a signed-in user back to the login screen.
  const [loading, setLoading] = useState(() => Boolean(tokens.access))

  useEffect(() => {
    if (!tokens.access) return
    authApi.me()
      .then(setUser)
      .catch(() => tokens.clear())
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onSignedOut = () => setUser(null)
    window.addEventListener('billing:signed-out', onSignedOut)
    return () => window.removeEventListener('billing:signed-out', onSignedOut)
  }, [])

  const login = useCallback(async (email, password) => {
    tokens.set(await authApi.login(email, password))
    setUser(await authApi.me())
  }, [])

  const logout = useCallback(() => {
    tokens.clear()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, loading, login, logout, isAdmin: user?.role === 'billing_admin' }}
    >
      {children}
    </AuthContext.Provider>
  )
}
