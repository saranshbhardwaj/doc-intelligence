//src/components/DataField.jsx
export default function DataField({ label, value, format = 'text' }) {
  const formatValue = (val) => {
    if (val === null || val === undefined || val === '') return 'N/A'
    if (format === 'currency') {
      const num = typeof val === 'string' ? parseFloat(val.replace(/[^0-9.-]+/g, '')) : val
      if (isNaN(num)) return val
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 }).format(num)
    }
    return val
  }

  return (
    <div className="bg-gray-50 p-3 rounded-lg">
      <div className="text-xs text-gray-600 mb-1 uppercase tracking-wide">{label}</div>
      <div className="text-base font-semibold text-gray-900">{formatValue(value)}</div>
    </div>
  )
}