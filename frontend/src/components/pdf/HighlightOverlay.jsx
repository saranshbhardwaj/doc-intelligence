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

  const x0 = Number(bbox.x0);
  const y0 = Number(bbox.y0);
  const x1 = Number(bbox.x1);
  const y1 = Number(bbox.y1);
  if (![x0, y0, x1, y1].every(Number.isFinite)) {
    return null;
  }

  // Convert inches to points (PDF standard: 72 points per inch)
  const POINTS_PER_INCH = 72;

  // Convert bbox from inches to points and normalize coordinate ordering.
  const x0Points = Math.min(x0, x1) * POINTS_PER_INCH;
  const y0Points = Math.min(y0, y1) * POINTS_PER_INCH;
  const x1Points = Math.max(x0, x1) * POINTS_PER_INCH;
  const y1Points = Math.max(y0, y1) * POINTS_PER_INCH;

  // Calculate position and size as percentages (for responsive rendering), clamped to page bounds.
  const left = Math.max(0, Math.min(100, (x0Points / pageWidth) * 100));
  const top = Math.max(0, Math.min(100, (y0Points / pageHeight) * 100));
  const width = Math.max(0, Math.min(100 - left, ((x1Points - x0Points) / pageWidth) * 100));
  const height = Math.max(0, Math.min(100 - top, ((y1Points - y0Points) / pageHeight) * 100));
  if (width <= 0 || height <= 0) {
    return null;
  }

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
