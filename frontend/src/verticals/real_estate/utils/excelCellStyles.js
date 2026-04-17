/**
 * Excel Cell Styling Utilities
 * Helper functions for extracting and applying Excel cell styles to React components
 */

/**
 * Calculate relative luminance of a hex color
 * Uses WCAG luminance formula to determine if text should be light or dark for contrast
 *
 * @param {string} hexColor - Hex color code (with or without #)
 * @returns {number} Luminance value between 0 and 1
 */
export function getLuminance(hexColor) {
  // Remove # if present
  const hex = hexColor.replace('#', '');

  // Parse RGB
  const r = parseInt(hex.substr(0, 2), 16) / 255;
  const g = parseInt(hex.substr(2, 2), 16) / 255;
  const b = parseInt(hex.substr(4, 2), 16) / 255;

  // Calculate relative luminance
  const [rs, gs, bs] = [r, g, b].map(c =>
    c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  );

  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

/**
 * Calculate WCAG contrast ratio between two hex colors.
 */
function getContrastRatio(hex1, hex2) {
  const l1 = getLuminance(hex1);
  const l2 = getLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// Well-known Excel theme color defaults (Office theme, indices 0-9)
const THEME_COLORS = [
  'FFFFFF', '000000', 'E7E6E6', '44546A', '4472C4',
  'ED7D31', 'A5A5A5', 'FFC000', '5B9BD5', '70AD47',
];

/**
 * Resolve an Excel color object (may have rgb, theme, or indexed) to a hex string.
 * Returns null if the color is transparent/white/absent.
 */
function resolveColor(colorObj) {
  if (!colorObj) return null;

  // Prefer explicit RGB
  if (colorObj.rgb) {
    const hex = colorObj.rgb.slice(-6); // strip alpha prefix if ARGB
    // Ignore transparent black (00000000) and pure white fill (FFFFFFFF / FFFFFF)
    if (hex === '000000' && colorObj.rgb.length === 8 && colorObj.rgb.startsWith('00')) return null;
    return `#${hex}`;
  }

  // Theme color fallback
  if (typeof colorObj.theme === 'number') {
    const base = THEME_COLORS[colorObj.theme];
    if (!base) return null;
    // tint: 0 = base color, positive = lighter, negative = darker
    if (colorObj.tint) {
      return `#${applyTint(base, colorObj.tint)}`;
    }
    return `#${base}`;
  }

  return null;
}

/**
 * Apply an Excel tint value (-1 to 1) to a base hex color.
 * Positive tint lightens toward white, negative darkens toward black.
 */
function applyTint(hex, tint) {
  const r = parseInt(hex.substr(0, 2), 16);
  const g = parseInt(hex.substr(2, 2), 16);
  const b = parseInt(hex.substr(4, 2), 16);

  const adjust = (c) => {
    if (tint > 0) return Math.round(c + (255 - c) * tint);
    return Math.round(c * (1 + tint));
  };

  return [adjust(r), adjust(g), adjust(b)]
    .map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Extract Excel cell styling and convert to CSS inline styles.
 * Handles background color (rgb + theme + tint), font styling,
 * and enforces minimum WCAG contrast so dark cells are readable in light mode.
 *
 * @param {Object} cell - XLSX cell object with styling metadata
 * @returns {Object} CSS inline style object
 */
export function getExcelCellStyle(cell) {
  if (!cell || !cell.s) return {};

  const style = {};

  // Excel fill: patternFill uses fgColor for solid fills; bgColor is the pattern background.
  // For solid fills (patternType === 'solid' or absent), fgColor is the cell background.
  // Fall back to bgColor if fgColor gives nothing useful.
  const bgHex = resolveColor(cell.s.fgColor) ?? resolveColor(cell.s.bgColor) ?? null;

  if (bgHex) {
    style.backgroundColor = bgHex;
  }

  // Font styling
  if (cell.s.font) {
    const font = cell.s.font;

    if (font.bold) style.fontWeight = 'bold';
    if (font.italic) style.fontStyle = 'italic';

    const fontColor = resolveColor(font.color);
    if (fontColor) style.color = fontColor;
  }

  // Enforce contrast against the rendered background.
  if (bgHex) {
    const isDarkBg = getLuminance(bgHex) < 0.5;
    const textColor = style.color;

    if (!textColor) {
      style.color = isDarkBg ? '#FFFFFF' : '#000000';
    } else {
      const ratio = getContrastRatio(bgHex, textColor);
      if (ratio < 4.5) {
        style.color = isDarkBg ? '#FFFFFF' : '#000000';
      }
    }
  }

  return style;
}
