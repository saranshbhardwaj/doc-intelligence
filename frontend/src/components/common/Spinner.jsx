// src/components/Spinner.jsx
import React from 'react'

export default function Spinner({ size = 10, text = 'Processing…' }) {
  const sizeClass = typeof size === 'number' ? `h-${size} w-${size}` : size
  return (
    <div className="flex flex-col items-center justify-center">
      <svg
        className="animate-spin h-10 w-10 text-blue-600 mb-4"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
      </svg>
      {text && <p className="text-sm text-gray-700">{text}</p>}
    </div>
  )
}
