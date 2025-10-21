// src/api.js
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_URL,
  timeout: 120_000, // 2 minutes
  headers: {
    // common headers if needed
  },
})

// exponential backoff helper
function sleep(ms) {
  return new Promise((res) => setTimeout(res, ms))
}

export async function uploadFile(file, { onUploadProgress, signal, maxRetries = 3 } = {}) {
  // Use FormData so backend receives as multipart/form-data
  const form = new FormData()
  form.append('file', file)

  let attempt = 0
  while (true) {
    try {
      const response = await api.post('/api/extract', form, {
        onUploadProgress,
        signal, // AbortController signal
        validateStatus: (s) => true, // we'll handle status
      })

      // handle 429 retry using Retry-After header
      if (response.status === 429) {
        attempt++
        const retryAfter = parseInt(response.headers['retry-after'] || '1', 10)
        const wait = Math.max(1000 * (isNaN(retryAfter) ? 1 : retryAfter) * attempt, 1000)
        if (attempt <= maxRetries) {
          await sleep(wait)
          continue
        }
      }

      // if non-2xx return object so caller can handle errors
      return response
    } catch (err) {
      // network or abort error
      if (axios.isCancel(err)) throw err
      attempt++
      if (attempt > maxRetries) throw err
      // backoff delay
      await sleep(500 * Math.pow(2, attempt))
    }
  }
}
