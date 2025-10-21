// src/App.jsx
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import FileUploader from './components/FileUploader'
import ResultsView from './components/ResultsView'

const queryClient = new QueryClient()

function AppInner() {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [rateLimit, setRateLimit] = useState(null)

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-gray-900 mb-4">📄 Sand Cloud</h1>
          <p className="text-xl text-gray-600 mb-2">Extract structured data from investment documents in seconds</p>
          <p className="text-sm text-gray-500">Free demo: 3 uploads per day • Max 30 pages • 5MB limit</p>
        </div>

        <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
          <FileUploader
            onResult={(data) => { setResult(data); setError(null) }}
            onError={(msg) => { setError(msg) }}
            setRateLimit={setRateLimit}
          />

          {rateLimit && rateLimit.remaining_uploads !== undefined && (
            <p className="mt-4 text-center text-sm text-gray-500">
              {rateLimit.remaining_uploads} upload{rateLimit.remaining_uploads !== 1 ? 's' : ''} remaining today
            </p>
          )}
        </div>

        {error && (
          <div className="bg-red-50 border-l-4 border-red-400 p-6 mb-8 rounded-r-lg" role="alert" aria-live="assertive">
            <h3 className="text-sm font-medium text-red-800">Error</h3>
            <p className="text-sm text-red-700 mt-1">{error}</p>
          </div>
        )}

        <ResultsView result={result} />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  )
}
