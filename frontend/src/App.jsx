import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('http://localhost:8000/health/')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        return response.json()
      })
      .then((json) => setData(json))
      .catch((err) => setError(err.message || 'Unable to reach backend'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <main className="health-page">
      <h1>Billing Backend Health</h1>

      {loading && <p>Loading backend status...</p>}

      {error && <p className="error">Backend unavailable: {error}</p>}

      {data && (
        <div className="health-card">
          <p>
            <strong>Service:</strong> {data.service}
          </p>
          <p>
            <strong>Status:</strong> {data.status}
          </p>
          <p>
            <strong>Message:</strong> {data.message}
          </p>
        </div>
      )}
    </main>
  )
}

export default App
