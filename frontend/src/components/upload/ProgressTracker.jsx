/**
 * ProgressTracker Component
 *
 * Displays real-time extraction progress with stage indicators and messages.
 * Uses Tailwind CSS for all styling.
 */

const STAGES = [
  { key: 'parsing', label: 'Parsing PDF', icon: '📄' },
  { key: 'chunking', label: 'Indexing Document', icon: '✂️' },
  { key: 'summarizing', label: 'Summarizing Sections', icon: '📝' },
  { key: 'extracting', label: 'Extracting Data', icon: '🤖' }
];

export default function ProgressTracker({ progress, error, onRetry }) {
  if (!progress && !error) {
    return null;
  }

  // Error state
  if (error) {
    // Authentication error - show login prompt
    if (error.type === 'auth_error') {
      return (
        <div className="mt-4 p-6 bg-gradient-to-br from-blue-400 via-blue-500 to-indigo-500 dark:from-blue-500 dark:via-blue-600 dark:to-indigo-600 rounded-xl text-white shadow-lg">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-3xl">🔒</span>
            <h3 className="text-xl font-semibold">Authentication Required</h3>
          </div>

          <div className="bg-white/20 rounded-lg p-4 mb-4">
            <p className="text-base font-medium mb-2">Please sign in to upload documents</p>
            <p className="text-sm opacity-90">
              You need to be logged in to use the document extraction service.
            </p>
          </div>

          <button
            onClick={() => window.location.href = '/sign-in'}
            className="w-full py-3 px-4 bg-white text-blue-600 rounded-lg font-semibold hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 active:translate-y-0"
          >
            🔑 Sign In / Sign Up
          </button>
        </div>
      );
    }

    // Page limit error - show upgrade prompt
    if (error.type === 'limit_error') {
      // Determine if it's a free tier one-time limit or paid tier monthly limit
      const isFreeLimit = error.message?.includes('Free tier');

      return (
        <div className="mt-4 p-6 bg-gradient-to-br from-orange-400 via-orange-500 to-red-500 dark:from-orange-500 dark:via-orange-600 dark:to-red-600 rounded-xl text-white shadow-lg">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-3xl">{isFreeLimit ? '🎁' : '📊'}</span>
            <h3 className="text-xl font-semibold">
              {isFreeLimit ? 'Free Trial Complete' : 'Page Limit Reached'}
            </h3>
          </div>

          <div className="bg-white/20 rounded-lg p-4 mb-4">
            <p className="text-base font-medium mb-2">{error.message}</p>
            <p className="text-sm opacity-90">
              {isFreeLimit
                ? "You've used all 100 free pages! Upgrade to continue analyzing documents."
                : "Upgrade your plan to process more documents this month."}
            </p>
          </div>

          <button
            onClick={() => window.location.href = '/#pricing'}
            className="w-full py-3 px-4 bg-white text-orange-600 rounded-lg font-semibold hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 active:translate-y-0"
          >
            🚀 {isFreeLimit ? 'View Pricing Plans' : 'Upgrade Plan'}
          </button>
        </div>
      );
    }

    // Generic error
    return (
      <div className="mt-4 p-6 bg-gradient-to-br from-pink-400 via-red-400 to-red-500 dark:from-pink-500 dark:via-red-500 dark:to-red-600 rounded-xl text-white shadow-lg">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-3xl">⚠️</span>
          <h3 className="text-xl font-semibold">Extraction Failed</h3>
        </div>

        <div className="bg-white/20 rounded-lg p-4 mb-4">
          <p className="text-base font-medium mb-2">{error.message}</p>
          {error.stage && (
            <p className="text-sm opacity-90">
              Failed at stage: <strong className="font-semibold">{error.stage}</strong>
            </p>
          )}
        </div>

        {error.isRetryable && onRetry && (
          <button
            onClick={onRetry}
            className="w-full py-3 px-4 bg-white text-red-500 rounded-lg font-semibold hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 active:translate-y-0"
          >
            🔄 Retry from Last Stage
          </button>
        )}
      </div>
    );
  }

  // Progress state
  const { percent, message, stages, stage } = progress;

  return (
    <div className="mt-4 p-6 bg-gradient-to-br from-purple-500 via-purple-600 to-indigo-600 dark:from-purple-600 dark:via-purple-700 dark:to-indigo-700 rounded-xl text-white shadow-lg">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-xl font-semibold">Processing Document</h3>
        <span className="text-2xl font-bold">{percent}%</span>
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-white/30 rounded-full overflow-hidden mb-4">
        <div
          className="h-full bg-white rounded-full transition-all duration-300 ease-out"
          style={{ width: `${percent}%` }}
        />
      </div>

      {/* Current message */}
      <p className="text-base mb-6 opacity-95">{message}</p>

      {/* Stage indicators */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {STAGES.map((stage) => {
          const isCompleted = stages?.[stage.key];
          const isCurrent = stage === stage.key;
          const isUpcoming = !isCompleted && !isCurrent;

          return (
            <div
              key={stage.key}
              className={`
                flex flex-col items-center text-center p-3 rounded-lg transition-all duration-300
                ${isCompleted ? 'bg-white/25' : ''}
                ${isCurrent ? 'bg-white/35 scale-105 shadow-lg' : ''}
                ${isUpcoming ? 'bg-white/10 opacity-60' : ''}
              `}
            >
              <div className="text-3xl mb-2">
                {isCompleted ? '✅' : stage.icon}
              </div>
              <div className="text-sm font-medium">{stage.label}</div>
              {isCurrent && (
                <div className="mt-1 text-xl animate-spin">⏳</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Completion state */}
      {percent === 100 && (
        <div className="mt-6 p-4 bg-white/20 rounded-lg text-center">
          <span className="text-2xl mr-2">🎉</span>
          <span className="text-lg font-semibold">Extraction complete!</span>
        </div>
      )}
    </div>
  );
}
