import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import CandidateDetailPanel from './CandidateDetailPanel';

function buildCandidate(overrides = {}) {
  return {
    id: 'candidate-1',
    name: 'Austin Mini Storage',
    market: 'Austin, TX',
    sourceName: 'Manual',
    assetClass: 'self_storage',
    assetClassConfidence: 91,
    underwritingRunId: null,
    facts: {},
    documents: [],
    evidence: [],
    ...overrides,
  };
}

describe('CandidateDetailPanel', () => {
  it('does not repeat the Attach from Library CTA when readiness already uses it as the primary action', () => {
    const markup = renderToStaticMarkup(
      <CandidateDetailPanel
        candidate={buildCandidate()}
        onCreateCandidate={vi.fn()}
        onOpenHandoff={vi.fn()}
        onOpenLibrary={vi.fn()}
        onOpenUnderwritingRun={vi.fn()}
        isPrototype={false}
      />,
    );

    expect(markup.match(/Attach from Library/g)).toHaveLength(1);
  });

  it('renders a remove action for attached Library documents', () => {
    const markup = renderToStaticMarkup(
      <CandidateDetailPanel
        candidate={buildCandidate({
          documents: [
            {
              id: 'link-1',
              document_id: 'doc-om',
              type: 'om',
              name: 'Deal OM.pdf',
              status: 'attached',
              processingStatus: 'completed',
              hasEmbeddings: true,
            },
          ],
        })}
        onCreateCandidate={vi.fn()}
        onDetachDocument={vi.fn()}
        onOpenHandoff={vi.fn()}
        onOpenLibrary={vi.fn()}
        onOpenUnderwritingRun={vi.fn()}
        isPrototype={false}
      />,
    );

    expect(markup).toContain('aria-label="Remove Deal OM.pdf"');
  });
});
