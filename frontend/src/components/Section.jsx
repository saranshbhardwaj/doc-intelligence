// src/components/Section.jsx
export function Section({ title, children }) {
    return (
      <div className="border-b border-gray-200 pb-6 last:border-b-0">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">{title}</h3>
        {children}
      </div>
    )
  }