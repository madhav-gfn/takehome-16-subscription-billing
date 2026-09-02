import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Filter state lives in the URL, not in component state. Three reasons, all of
 * which matter for this brief: a filtered view is shareable and bookmarkable,
 * the back button works, and it is self-evident that filtering happens on the
 * server — the URL changes and a request goes out.
 */
export function useQueryFilters(defaults = {}) {
  const [params, setParams] = useSearchParams()

  const filters = useMemo(() => {
    const out = { ...defaults }
    for (const key of new Set(params.keys())) {
      const all = params.getAll(key)
      out[key] = all.length > 1 || key === 'status' ? all : all[0]
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  const setFilter = useCallback((key, value) => {
    const next = new URLSearchParams(params)
    next.delete(key)
    if (Array.isArray(value)) {
      value.forEach((v) => next.append(key, v))
    } else if (value !== '' && value != null && value !== false) {
      next.set(key, value)
    }
    // Any filter change resets to page 1 — otherwise a user lands on page 7 of
    // a 2-page result and sees an empty table.
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }, [params, setParams])

  const clear = useCallback(() => setParams(new URLSearchParams()), [setParams])

  const queryString = useMemo(() => {
    const qs = params.toString()
    return qs ? `?${qs}` : ''
  }, [params])

  return { filters, setFilter, clear, queryString, params }
}
