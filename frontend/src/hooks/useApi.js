import { useCallback, useEffect, useRef, useState } from 'react'
import { get } from '../api/client'

export function useApi(path, { skip = false } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  // Free-tier hosting sleeps when idle; a spinner that explains itself reads as
  // considered, a silent 45-second spinner reads as broken.
  const [slow, setSlow] = useState(false)
  const [nonce, setNonce] = useState(0)
  const latest = useRef(0)

  useEffect(() => {
    if (skip || !path) return
    const id = ++latest.current
    const timer = setTimeout(() => setSlow(true), 5000)

    get(path)
      .then((res) => {
        // Guard against out-of-order responses: typing in the debounced search
        // box fires several requests, and a slow earlier one must not
        // overwrite a fast later one.
        if (id === latest.current) {
          setData(res)
          setLoading(false)
          setError(null)
        }
      })
      .catch((err) => {
        if (id === latest.current) {
          setData(null)
          setLoading(false)
          setError(err)
        }
      })
      .finally(() => {
        clearTimeout(timer)
        if (id === latest.current) setSlow(false)
      })

    return () => clearTimeout(timer)
  }, [path, skip, nonce])

  const refetch = useCallback(() => {
    setLoading(true)
    setNonce((n) => n + 1)
  }, [])

  const isLoading = !skip && Boolean(path) && (loading || (data === null && error === null))

  return { data, loading: isLoading, error, slow, refetch }
}

/** For imperative actions: tracks pending state and surfaces the API error. */
export function useAction() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)

  const run = useCallback(async (fn) => {
    setPending(true)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      setError(e)
      throw e
    } finally {
      setPending(false)
    }
  }, [])

  return { run, pending, error, clearError: () => setError(null) }
}
