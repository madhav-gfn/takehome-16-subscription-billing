import { useCallback, useEffect, useRef, useState } from 'react'
import { get } from '../api/client'

export function useApi(path, { skip = false } = {}) {
  const [state, setState] = useState({ data: null, loading: !skip, error: null })
  // Free-tier hosting sleeps when idle; a spinner that explains itself reads as
  // considered, a silent 45-second spinner reads as broken.
  const [slow, setSlow] = useState(false)
  const latest = useRef(0)

  const refetch = useCallback(() => {
    if (skip || !path) return
    const id = ++latest.current
    setState((s) => ({ ...s, loading: true, error: null }))
    const timer = setTimeout(() => setSlow(true), 5000)

    get(path)
      .then((data) => {
        // Guard against out-of-order responses: typing in the debounced search
        // box fires several requests, and a slow earlier one must not
        // overwrite a fast later one.
        if (id === latest.current) setState({ data, loading: false, error: null })
      })
      .catch((error) => {
        if (id === latest.current) setState({ data: null, loading: false, error })
      })
      .finally(() => {
        clearTimeout(timer)
        if (id === latest.current) setSlow(false)
      })
  }, [path, skip])

  useEffect(() => { refetch() }, [refetch])

  return { ...state, slow, refetch }
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
