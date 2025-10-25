// src/components/Section.jsx
export default function Section({ title, icon: Icon, children, highlight = false }) {
  return (
    <div className={`bg-white rounded-xl shadow-md overflow-hidden border-l-4 ${
      highlight ? 'border-blue-600' : 'border-gray-200'
    }`}>
      <div className={`px-6 py-4 ${highlight ? 'bg-gradient-to-r from-blue-50 to-white' : 'bg-gray-50'} border-b border-gray-200`}>
        <div className="flex items-center gap-3">
          {Icon && <Icon className={`w-6 h-6 ${highlight ? 'text-blue-600' : 'text-gray-600'}`} />}
          <h3 className="text-xl font-bold text-gray-800">{title}</h3>
        </div>
      </div>
      <div className="px-6 py-5">
        {children}
      </div>
    </div>
  );
}