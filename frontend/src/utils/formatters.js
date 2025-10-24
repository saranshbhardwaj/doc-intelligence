// src/utils/formatters.js
export const safeText = (text) => {
    if (text == null) return 'N/A';
    return String(text);
  };
  
  export const formatCurrency = (value, currency = 'USD') => {
    if (value == null) return 'N/A';
    const num = Number(value);
    if (num >= 1000000000) {
      return `$${(num / 1000000000).toFixed(2)}B`;
    } else if (num >= 1000000) {
      return `$${(num / 1000000).toFixed(2)}M`;
    } else if (num >= 1000) {
      return `$${(num / 1000).toFixed(2)}K`;
    }
    return `$${num.toFixed(2)}`;
  };
  
  export const formatPercentage = (value) => {
    if (value == null) return 'N/A';
    return `${(Number(value) * 100).toFixed(1)}%`;
  };
  
  export const sortYearKeysDesc = (keys) => {
    return keys.sort((a, b) => {
      const yearA = parseInt(a.replace('projected_', ''));
      const yearB = parseInt(b.replace('projected_', ''));
      return yearB - yearA;
    });
  };