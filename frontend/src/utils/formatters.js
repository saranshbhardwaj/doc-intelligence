// src/utils/formatters.js
export const safeText = (text) => {
    if (text == null) return 'N/A';
    // Handle objects - don't render as "[object Object]"
    if (typeof text === 'object' && !Array.isArray(text)) {
      console.warn('safeText received an object:', text);
      return 'N/A';
    }
    // Handle arrays
    if (Array.isArray(text)) {
      return text.join(', ');
    }
    return String(text);
  };
  
  // Currency symbol mapper
  const CURRENCY_SYMBOLS = {
    'USD': '$',
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥',
    'CNY': '¥',
    'CHF': 'CHF',
    'CAD': 'C$',
    'AUD': 'A$',
    'NZD': 'NZ$',
    'INR': '₹',
    'SEK': 'kr',
    'NOK': 'kr',
    'DKK': 'kr',
    'ISK': 'kr',
    'KRW': '₩',
    'BRL': 'R$',
    'MXN': 'Mex$',
    'ZAR': 'R',
    'SGD': 'S$',
    'HKD': 'HK$',
    'PLN': 'zł',
    'THB': '฿',
    'TRY': '₺',
    'RUB': '₽',
    'AED': 'AED',
    'SAR': 'SAR',
  };

  export const formatCurrency = (value, currency = 'USD') => {
    if (value == null) return 'N/A';
    const num = Number(value);
    const isNegative = num < 0;
    const absNum = Math.abs(num);

    // Normalize currency code to uppercase
    const currencyCode = currency ? currency.toUpperCase() : 'USD';

    // Get symbol, fallback to currency code if not in map
    const symbol = CURRENCY_SYMBOLS[currencyCode] || currencyCode;

    // Determine if symbol goes before or after the number
    // Most currencies go before, except for some like SEK, NOK, DKK, ISK
    const symbolAfter = ['SEK', 'NOK', 'DKK', 'ISK'].includes(currencyCode);

    let formatted;
    if (absNum >= 1000000000) {
      formatted = `${(absNum / 1000000000).toFixed(2)}B`;
    } else if (absNum >= 1000000) {
      formatted = `${(absNum / 1000000).toFixed(2)}M`;
    } else if (absNum >= 1000) {
      formatted = `${(absNum / 1000).toFixed(2)}K`;
    } else {
      formatted = `${absNum.toFixed(2)}`;
    }

    // Add symbol before or after based on currency convention
    const withSymbol = symbolAfter ? `${formatted} kr` : `${symbol}${formatted}`;

    return isNegative ? `-${withSymbol}` : withSymbol;
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