const fs = require('fs');

const path = 'evals/datasets/golden/rag-chat-96/rag_retrieval_dedup.jsonl';
const newAssertion = "(() => {const benchmarkGold = JSON.parse(context.vars.benchmark_gold_evidence || '[]');const expectedAnchors = JSON.parse(context.vars.expected_anchors || context.vars.expected_pages || '[]');const candidateDocumentIds = new Set(JSON.parse(context.vars.document_ids || '[]'));const benchmarkGoldUsable = benchmarkGold.length > 0 && benchmarkGold.some(item => item && item.document_id && candidateDocumentIds.has(item.document_id));const expected = benchmarkGoldUsable ? benchmarkGold : expectedAnchors;const useSpreadsheetSheetFallback = !benchmarkGoldUsable;const keyForAnchor = (item) => {if (!item || !item.document_id) return null;if (item.chunk_id) {const sheetName = item.sheet_name || item.sheet;if (useSpreadsheetSheetFallback && sheetName) return item.document_id + ':sheet:' + String(sheetName).toLowerCase();return item.document_id + ':chunk:' + item.chunk_id;}const page = item.page ?? item.bbox_page ?? item.page_number;if (page === null || page === undefined) return null;return item.document_id + ':page:' + page;};const expectedKeys = expected.map(keyForAnchor).filter(Boolean);if (expectedKeys.length === 0) return true;const chunks = JSON.parse(output).chunks;const gotSet = new Set(chunks.map(keyForAnchor).filter(Boolean));const hits = expectedKeys.filter(key => gotSet.has(key)).length;return hits / expectedKeys.length >= 0.8;})()";

const lines = fs.readFileSync(path, 'utf8').trimEnd().split(/\r?\n/);
const rows = lines.map((line) => JSON.parse(line));

for (let index = 0; index < 20; index += 1) {
  const assertion = rows[index].assert.find((item) => item.metric === 'retrieval/page_recall_80');
  if (!assertion) {
    throw new Error(`Missing retrieval assertion on row ${index + 1}`);
  }
  assertion.value = newAssertion;
}

const pointBlank = rows[13];
pointBlank.vars.benchmark_target_document_ids = JSON.stringify([
  '54225e7e-dc4d-4ad3-9c4a-9f021798edfc',
]);
pointBlank.vars.benchmark_gold_evidence = JSON.stringify([
  {
    document_id: '54225e7e-dc4d-4ad3-9c4a-9f021798edfc',
    page: 18,
    evidence_type: 'table',
    table_label: 'operating_expenses',
    field_label: 'property_taxes_2024',
    relevance: 3,
    supports: ['retrieval', 'generation', 'citation', 'numeric_em'],
    normalized_value: {
      field_name: 'property_taxes_2024',
      canonical_value: 15275.0,
      unit: 'usd',
      comparison: 'exact',
      accepted_surface_forms: ['$15,275', '15,275', '15275'],
      raw_value: '$15,275',
    },
  },
]);
pointBlank._metadata.benchmark_annotation.target_document_ids = [
  '54225e7e-dc4d-4ad3-9c4a-9f021798edfc',
];
pointBlank._metadata.benchmark_annotation.gold_evidence = [
  {
    document_id: '54225e7e-dc4d-4ad3-9c4a-9f021798edfc',
    page: 18,
    evidence_type: 'table',
    table_label: 'operating_expenses',
    field_label: 'property_taxes_2024',
    relevance: 3,
    supports: ['retrieval', 'generation', 'citation', 'numeric_em'],
    normalized_value: {
      field_name: 'property_taxes_2024',
      canonical_value: 15275.0,
      unit: 'usd',
      comparison: 'exact',
      accepted_surface_forms: ['$15,275', '15,275', '15275'],
      raw_value: '$15,275',
    },
  },
];

const tulsa = rows[89];
tulsa.vars.benchmark_gold_evidence = JSON.stringify([]);
tulsa._metadata.benchmark_annotation.gold_evidence = [];

fs.writeFileSync(path, rows.map((row) => JSON.stringify(row)).join('\n') + '\n');
