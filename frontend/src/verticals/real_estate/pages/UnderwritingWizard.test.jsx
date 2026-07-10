import { describe, expect, it } from 'vitest';
import {
  buildExtractionDocuments,
  buildSelectedDoc,
  buildSelectedDocsFromRun,
  hydrateProjectDataFromRun,
} from '../utils/underwritingDocuments';

describe('UnderwritingWizard source document hydration', () => {
  it('hydrates source document slots before extraction inputs exist', () => {
    const selectedDocs = buildSelectedDocsFromRun({
      id: 'run-1',
      status: 'needs_review',
      inputs: null,
      document_ids: [
        { document_id: 'doc-om', doc_type: 'om' },
        { document_id: 'doc-t12', doc_type: 't12' },
        { document_id: 'doc-rr', doc_type: 'rent_roll' },
      ],
    });

    expect(selectedDocs.om).toMatchObject({ document_id: 'doc-om', doc_type: 'om', name: 'Offering Memorandum' });
    expect(selectedDocs.t12).toMatchObject({ document_id: 'doc-t12', doc_type: 't12', name: 'T-12 / T-6 Statement' });
    expect(selectedDocs.rent_roll).toMatchObject({ document_id: 'doc-rr', doc_type: 'rent_roll', name: 'Rent Roll' });
  });

  it('hydrates deal name before extraction inputs exist so Run extraction can unlock', () => {
    const projectData = hydrateProjectDataFromRun(
      { name: '', address: '', asset_type: 'self_storage' },
      { id: 'run-1', name: 'Tulsa Deal 169', address: '1540 North Yale Avenue', inputs: null },
    );

    expect(projectData).toMatchObject({
      name: 'Tulsa Deal 169',
      address: '1540 North Yale Avenue',
      asset_type: 'self_storage',
    });
  });

  it('uses source document filenames when run detail includes metadata', () => {
    const selectedDocs = buildSelectedDocsFromRun({
      source_documents: [
        { document_id: 'doc-om', doc_type: 'om', filename: 'Deal OM.pdf' },
      ],
    });

    expect(selectedDocs.om).toMatchObject({ document_id: 'doc-om', doc_type: 'om', name: 'Deal OM.pdf' });
  });

  it('keeps the manual wizard flow mapping selected documents into extraction payloads', () => {
    const selectedDocs = {
      om: buildSelectedDoc('om', { id: 'doc-om', filename: 'Manual OM.pdf' }),
      t12: buildSelectedDoc('t12', { id: 'doc-t12', filename: 'Manual T12.xlsx' }),
      rent_roll: buildSelectedDoc('rent_roll', { id: 'doc-rr', filename: 'Manual Rent Roll.xlsx' }),
    };

    expect(selectedDocs.om).toMatchObject({ document_id: 'doc-om', doc_type: 'om', name: 'Manual OM.pdf' });
    expect(buildExtractionDocuments(selectedDocs)).toEqual([
      { document_id: 'doc-om', doc_type: 'om' },
      { document_id: 'doc-t12', doc_type: 't12' },
      { document_id: 'doc-rr', doc_type: 'rent_roll' },
    ]);
  });
});
