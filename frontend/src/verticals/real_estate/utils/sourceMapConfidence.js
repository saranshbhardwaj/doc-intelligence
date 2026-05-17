// Mirrors backend/app/verticals/real_estate/template_filling/source_map.py constants.
// Deliberately stricter than ExcelGrid's 0.80/0.50 — these values drive gating decisions
// (structure_key_missing, low_structure_confidence), not just display color.
export const STRUCTURE_HIGH_CONFIDENCE = 0.85;
export const STRUCTURE_LOW_CONFIDENCE = 0.60;

export function tierForConfidence(c) {
  if (c == null) return 'unknown';
  if (c >= STRUCTURE_HIGH_CONFIDENCE) return 'high';
  if (c >= STRUCTURE_LOW_CONFIDENCE) return 'mid';
  return 'low';
}
