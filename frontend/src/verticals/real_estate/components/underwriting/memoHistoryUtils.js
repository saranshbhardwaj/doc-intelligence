export function getLatestMemo(memos = []) {
  if (!Array.isArray(memos) || memos.length === 0) return null;
  return [...memos].sort((a, b) => Number(b.version || 0) - Number(a.version || 0))[0];
}

export function formatMemoDate(value) {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Date unavailable';
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export function getMemoWarningLabel(warnings = []) {
  const count = Array.isArray(warnings) ? warnings.length : 0;
  if (!count) return null;
  return `${count} warning${count === 1 ? '' : 's'}`;
}

export function getMemoStatusTone(status) {
  if (status === 'complete') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'pending' || status === 'generating' || status === 'running' || status === 'processing') return 'active';
  return 'neutral';
}

export function getMemoStatusLabel(status) {
  const labels = {
    complete: 'Complete',
    failed: 'Failed',
    pending: 'Queued',
    generating: 'Generating',
    running: 'Generating',
    processing: 'Generating',
    queued: 'Queued',
  };
  return labels[status] || status || 'Unknown';
}

export function canDownloadMemo(memo) {
  return memo?.status === 'complete';
}

export function canDeleteMemo(memo) {
  return memo?.status === 'complete' || memo?.status === 'failed';
}
