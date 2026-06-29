const SEVERITY_RANK = { critical: 0, warning: 1, info: 2 };

export function sortGateFindings(findings = []) {
  return [...findings].sort((a, b) => {
    const rankDelta = (SEVERITY_RANK[a?.severity] ?? 3) - (SEVERITY_RANK[b?.severity] ?? 3);
    if (rankDelta !== 0) return rankDelta;
    return String(a?.id || '').localeCompare(String(b?.id || ''));
  });
}

export function flattenGateFindings(gates = []) {
  return gates.flatMap((gate) =>
    sortGateFindings(gate.findings || []).map((finding) => ({
      ...finding,
      gate_id: gate.id,
      gate_label: gate.label,
    })),
  );
}

export function getBlockingGateSummary(workflow) {
  const gateIds = workflow?.memo_generation?.blocking_gate_ids || [];
  const gates = workflow?.gates || [];
  return gateIds.map((id) => gates.find((gate) => gate.id === id)?.label || id);
}

export function requiresMemoOverride(workflow) {
  return Boolean(workflow?.memo_generation?.requires_override);
}