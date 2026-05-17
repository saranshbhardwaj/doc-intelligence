import { describe, expect, it } from 'vitest';
import { shouldShowLargeDocumentContextWarning } from './templateFillWarnings';

describe('shouldShowLargeDocumentContextWarning', () => {
  it('hides the large-document banner for a normal 30-page OM even when context was narrowed', () => {
    const fillRun = {
      document_metadata: { page_count: 30 },
      field_mapping: {
        context_budget: { user_warning: 'Large document: prompt context narrowed.' },
      },
    };

    expect(shouldShowLargeDocumentContextWarning(fillRun)).toBe(false);
  });

  it('shows the banner for 80+ page documents when a context warning exists', () => {
    const fillRun = {
      document_metadata: { page_count: 80 },
      field_mapping: {
        context_budget: { user_warning: 'Large document: prompt context narrowed.' },
      },
    };

    expect(shouldShowLargeDocumentContextWarning(fillRun)).toBe(true);
  });
});
