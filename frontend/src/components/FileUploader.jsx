// src/components/FileUploader.jsx
import { useRef, useState, useEffect } from 'react'
import { uploadFile } from '../api'
import classNames from 'classnames'

export default function FileUploader({ onResult, onError, setRateLimit }) {
  const [file, setFile] = useState(null)
  const [progress, setProgress] = useState(0)
  const [loading, setLoading] = useState(false)
  const [localError, setLocalError] = useState(null)
  const controllerRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    return () => {
      if (controllerRef.current) controllerRef.current.abort()
    }
  }, [])

  const validate = (f) => {
    if (!f) return 'No file selected'
    if (f.type !== 'application/pdf') return 'Please select a PDF file'
    if (f.size > 5 * 1024 * 1024) return 'File too large. Maximum size is 5MB.'
    // optionally add page count check with pdfjs in the future
    return null
  }

  const handleFile = (f) => {
    const err = validate(f)
    if (err) {
      setLocalError(err)
      return
    }
    setFile(f)
    setLocalError(null)
  }

  const onDrop = (e) => {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f) handleFile(f)
  }

  const onChoose = (e) => {
    const f = e.target.files?.[0]
    if (f) handleFile(f)
  }

  const upload = async () => {
    if (!file) return
    setLoading(true)
    setProgress(0)
    setLocalError(null)
    controllerRef.current = new AbortController()
    try {
      const resp = await uploadFile(file, {
        onUploadProgress: (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100))
        },
        signal: controllerRef.current.signal,
      })

      if (!resp || resp.status >= 400) {
        // try to show backend detail
        const body = resp?.data
        if (resp?.status === 429) {
          onError(`Rate limit exceeded. ${body?.detail?.message || ''}`)
          setRateLimit(body?.rate_limit || null)
        } else {
          onError(body?.detail || `Upload failed (${resp?.status})`)
        }
        return
      }

      // success
      onResult(resp.data)
      setRateLimit(resp.data?.rate_limit || null)
    } catch (err) {
      if (err.name === 'CanceledError' || err.message === 'canceled') {
        onError('Upload canceled.')
      } else {
        onError(`Network error: ${err.message}`)
      }
    } finally {
      setLoading(false)
      controllerRef.current = null
    }
  }

  return (
    <div>
      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        className={classNames('border-2 border-dashed rounded-lg p-6 text-center', {
          'border-blue-400': !!file,
        })}
      >
        <input ref={inputRef} id="file-input" type="file" accept="application/pdf" onChange={onChoose} className="hidden" />
        <label htmlFor="file-input" className="cursor-pointer block">
          <div className="flex flex-col items-center">
            <svg className="w-12 h-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <div className="text-sm text-gray-600">Click to select or drag and drop a PDF</div>
            <div className="text-xs text-gray-500 mt-1">PDF up to 5MB</div>
          </div>
        </label>
      </div>

      {localError && <div className="text-red-600 mt-3">{localError}</div>}

      {file && (
        <div className="mt-4 p-3 bg-blue-50 rounded flex items-center justify-between">
          <div>
            <div className="font-medium text-gray-900">{file.name}</div>
            <div className="text-xs text-gray-600">{(file.size / 1024).toFixed(0)} KB</div>
          </div>

          <div className="flex items-center gap-3">
            {loading ? (
              <div className="w-48">
                <div className="h-2 bg-gray-200 rounded">
                  <div className="h-2 bg-blue-600 rounded" style={{ width: `${progress}%` }} />
                </div>
                <div className="text-xs text-gray-600 mt-1">{progress}%</div>
              </div>
            ) : null}

            {!loading && (
              <>
                <button onClick={() => setFile(null)} className="text-gray-500 hover:text-gray-700">Remove</button>
                <button onClick={upload} className="bg-blue-600 text-white px-4 py-2 rounded">Upload</button>
              </>
            )}

            {loading && (
              <button onClick={() => controllerRef.current?.abort()} className="bg-red-100 text-red-700 px-3 py-1 rounded">Cancel</button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
