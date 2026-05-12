export const LARGE_DOCUMENT_PAGE_THRESHOLD = 80;

export function shouldShowLargeDocumentContextWarning(fillRun) {
  const warning = fillRun?.field_mapping?.context_budget?.user_warning;
  const pageCount = Number(fillRun?.document_metadata?.page_count ?? 0);
  return Boolean(warning) && pageCount >= LARGE_DOCUMENT_PAGE_THRESHOLD;
}
