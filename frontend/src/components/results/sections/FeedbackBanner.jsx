// src/components/results/sections/FeedbackBanner.jsx
export default function FeedbackBanner({ onFeedbackClick }) {
  return (
    <div className="bg-card rounded-xl shadow-md overflow-hidden">
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/30 dark:to-indigo-900/30 p-6 flex items-start gap-4">
        <div className="flex-shrink-0">
          <svg
            className="w-8 h-8 text-blue-600 dark:text-blue-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
            />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-foreground dark:text-gray-100 mb-1">
            Was this extraction helpful?
          </h3>
          <p className="text-sm text-muted-foreground dark:text-muted-foreground mb-3">
            Your feedback helps us improve accuracy and add features you need.
          </p>
          <button
            onClick={onFeedbackClick}
            className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1"
          >
            Share your thoughts
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
