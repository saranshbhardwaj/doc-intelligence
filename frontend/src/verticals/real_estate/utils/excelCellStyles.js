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
 * Extract Excel cell styling and convert to CSS inline styles
 * Handles background color, font styling, and auto text color for contrast
 *
 * @param {Object} cell - XLSX cell object with styling metadata
 * @returns {Object} CSS inline style object
 */
export function getExcelCellStyle(cell) {
  if (!cell || !cell.s) return {};

  const style = {};

  // Background color
  if (cell.s.fgColor) {
    const rgb = cell.s.fgColor.rgb;
    if (rgb) {
      const bgColor = `#${rgb}`;
      style.backgroundColor = bgColor;

      // Auto-adjust text color for contrast if no explicit font color
      if (!cell.s.font || !cell.s.font.color) {
        const luminance = getLuminance(bgColor);
        // If background is dark (luminance < 0.5), use white text
        style.color = luminance < 0.5 ? '#FFFFFF' : '#000000';
      }
    }
  }

  // Font styling
  if (cell.s.font) {
    const font = cell.s.font;

    // Font weight (bold)
    if (font.bold) {
      style.fontWeight = 'bold';
    }

    // Font style (italic)
    if (font.italic) {
      style.fontStyle = 'italic';
    }

    // Font color (overrides auto-calculated color)
    if (font.color && font.color.rgb) {
      style.color = `#${font.color.rgb}`;
    }
  }

  return style;
}
