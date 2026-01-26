/**
 * HighlightOverlay Component
 * Renders a semi-transparent rectangle overlay on PDF to highlight specific regions
 *
 * Coordinate System:
 * - bbox coordinates are in inches from Azure Document Intelligence
 * - Converts to percentage-based positioning for responsive rendering
 */

import React from 'react';

export default function HighlightOverlay({
  bbox,          // { page, x0, y0, x1, y1 } in inches
  pageWidth,     // PDF page width in points (72 points = 1 inch)
  pageHeight,    // PDF page height in points
  scale = 1,     // Current zoom scale
  onClick
}) {
  if (!bbox || !pageWidth || !pageHeight) {
    return null;
  }

  // Convert inches to points (PDF standard: 72 points per inch)
  const POINTS_PER_INCH = 72;

  // Convert bbox from inches to points
  const x0Points = bbox.x0 * POINTS_PER_INCH;
  const y0Points = bbox.y0 * POINTS_PER_INCH;
  const x1Points = bbox.x1 * POINTS_PER_INCH;
  const y1Points = bbox.y1 * POINTS_PER_INCH;

  // Calculate position and size as percentages (for responsive rendering)
  const left = (x0Points / pageWidth) * 100;
  const top = (y0Points / pageHeight) * 100;
  const width = ((x1Points - x0Points) / pageWidth) * 100;
  const height = ((y1Points - y0Points) / pageHeight) * 100;

  return (
    <div
      className="absolute border-2 border-primary bg-primary/20 rounded cursor-pointer
                 transition-all duration-300 animate-message-glow hover:bg-primary/30
                 pointer-events-auto z-10"
      style={{
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`,
      }}
      onClick={onClick}
      title="Click to clear highlight"
    />
  );
}
