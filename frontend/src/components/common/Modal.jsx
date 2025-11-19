// frontend/src/components/Modal.jsx
export default function Modal({ isOpen, onClose, title, children }) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto"
      aria-labelledby="modal-title"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-card0  bg-opacity-75 dark:bg-opacity-75 transition-opacity"
        onClick={onClose}
      ></div>

      {/* Modal */}
      <div className="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
        <div className="relative transform overflow-hidden rounded-lg bg-card text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg">
          {/* Content */}
          <div className="bg-card px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
            {/* If title is provided, show header */}
            {title && (
              <div className="flex items-center justify-between mb-4">
                <h3
                  className="text-lg font-semibold text-foreground"
                  id="modal-title"
                >
                  {title}
                </h3>
                <button
                  onClick={onClose}
                  className="text-muted-foreground hover:text-muted-foreground dark:hover:text-gray-300 focus:outline-none"
                >
                  <svg
                    className="h-6 w-6"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>
            )}

            {/* Content */}
            <div>{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
