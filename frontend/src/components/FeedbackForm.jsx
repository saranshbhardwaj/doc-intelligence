// frontend/src/components/FeedbackForm.jsx
import { useState } from 'react'

export default function FeedbackForm({ requestId, onClose }) {
  const [rating, setRating] = useState(0)
  const [accuracyRating, setAccuracyRating] = useState(0)
  const [wouldPay, setWouldPay] = useState(null)
  const [comment, setComment] = useState('')
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (rating === 0) {
      alert('Please provide a rating')
      return
    }

    setSubmitting(true)

    try {
      const response = await fetch(`${API_URL}/api/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          rating,
          accuracy_rating: accuracyRating || null,
          would_pay: wouldPay,
          comment: comment.trim() || null,
          email: email.trim() || null
        })
      })

      if (!response.ok) {
        throw new Error('Failed to submit feedback')
      }

      setSubmitted(true)
      setTimeout(() => {
        onClose()
      }, 2000)

    } catch (error) {
      alert('Failed to submit feedback. Please try again.')
      console.error(error)
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <div className="text-center py-8">
        <div className="mb-4">
          <svg className="w-16 h-16 text-green-500 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h3 className="text-xl font-semibold text-gray-900 mb-2">Thank you!</h3>
        <p className="text-gray-600">Your feedback helps us improve.</p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Overall Rating */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Overall Experience *
        </label>
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              type="button"
              onClick={() => setRating(star)}
              className="focus:outline-none"
            >
              <svg
                className={`w-10 h-10 ${
                  star <= rating ? 'text-yellow-400 fill-current' : 'text-gray-300'
                } hover:text-yellow-400 transition-colors`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                />
              </svg>
            </button>
          ))}
        </div>
        {rating > 0 && (
          <p className="text-sm text-gray-500 mt-1">
            {rating === 5 && '⭐ Excellent!'}
            {rating === 4 && '👍 Good'}
            {rating === 3 && '😐 Okay'}
            {rating === 2 && '👎 Poor'}
            {rating === 1 && '😞 Very Poor'}
          </p>
        )}
      </div>

      {/* Accuracy Rating */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          How accurate was the extraction?
        </label>
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              type="button"
              onClick={() => setAccuracyRating(star)}
              className="focus:outline-none"
            >
              <svg
                className={`w-8 h-8 ${
                  star <= accuracyRating ? 'text-blue-400 fill-current' : 'text-gray-300'
                } hover:text-blue-400 transition-colors`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </button>
          ))}
        </div>
      </div>

      {/* Would Pay */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Would you pay for unlimited access?
        </label>
        <div className="flex gap-4">
          <button
            type="button"
            onClick={() => setWouldPay(true)}
            className={`flex-1 py-2 px-4 rounded-lg border-2 transition-colors ${
              wouldPay === true
                ? 'border-green-500 bg-green-50 text-green-700'
                : 'border-gray-300 text-gray-700 hover:border-green-300'
            }`}
          >
            👍 Yes
          </button>
          <button
            type="button"
            onClick={() => setWouldPay(false)}
            className={`flex-1 py-2 px-4 rounded-lg border-2 transition-colors ${
              wouldPay === false
                ? 'border-red-500 bg-red-50 text-red-700'
                : 'border-gray-300 text-gray-700 hover:border-red-300'
            }`}
          >
            👎 No
          </button>
        </div>
      </div>

      {/* Comment */}
      <div>
        <label htmlFor="comment" className="block text-sm font-medium text-gray-700 mb-2">
          Comments or suggestions
        </label>
        <textarea
          id="comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={4}
          maxLength={1000}
          placeholder="What worked well? What could be improved?"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <p className="text-xs text-gray-500 mt-1">{comment.length}/1000 characters</p>
      </div>

      {/* Email (optional) */}
      <div>
        <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
          Email (optional - for follow-up)
        </label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="your@email.com"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      {/* Submit Buttons */}
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting || rating === 0}
          className="flex-1 bg-blue-600 text-white py-3 px-6 rounded-lg font-semibold
            hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed
            transition-colors"
        >
          {submitting ? 'Submitting...' : 'Submit Feedback'}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="px-6 py-3 border border-gray-300 rounded-lg text-gray-700
            hover:bg-gray-50 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}