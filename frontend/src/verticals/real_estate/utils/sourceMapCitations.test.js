import { describe, expect, it } from 'vitest';
import { groupSourceMapCitationsByPage } from './sourceMapCitations';

describe('groupSourceMapCitationsByPage', () => {
  it('collapses citations from the same page and preserves count metadata', () => {
    const groups = groupSourceMapCitationsByPage([
      '[D298:p22]',
      '[D303:p22]',
      '[D308:p22]',
      '[D353:p29]',
    ]);

    expect(groups).toEqual([
      {
        page: 22,
        citations: ['[D298:p22]', '[D303:p22]', '[D308:p22]'],
        primaryCitation: '[D298:p22]',
        label: 'Page 22 · 3 citations',
      },
      {
        page: 29,
        citations: ['[D353:p29]'],
        primaryCitation: '[D353:p29]',
        label: 'Page 29',
      },
    ]);
  });
});
