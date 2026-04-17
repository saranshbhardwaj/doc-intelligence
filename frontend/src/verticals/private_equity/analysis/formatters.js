import {
  ANALYSIS_CATEGORY_LABELS,
  ASSESSMENT_LABELS,
  COVERAGE_STATUS_LABELS,
  COVERAGE_WORKSTREAM_LABELS,
  FINDING_STATUS_LABELS,
} from "./displayConstants";

export function getCoverageWorkstreamLabel(category) {
  return COVERAGE_WORKSTREAM_LABELS[category] || category.replace(/_/g, " ");
}

export function getCoverageStatusLabel(status) {
  return COVERAGE_STATUS_LABELS[status] || status;
}

export function getAnalysisCategoryLabel(category) {
  return ANALYSIS_CATEGORY_LABELS[category] || category.replace(/_/g, " ");
}

export function getFindingStatusLabel(status) {
  return FINDING_STATUS_LABELS[status] || status;
}

export function getAssessmentLabel(assessment) {
  return ASSESSMENT_LABELS[assessment] || assessment.replace(/_/g, " ");
}

export function humanizeLabel(value) {
  return value ? value.replace(/_/g, " ") : value;
}

export function getFindingWorkstream(finding) {
  const category = finding?.category;
  if (category === "contract") return "transaction_legal";
  if (category === "commercial") return "commercial";
  if (category === "debt") return "debt_financing";
  if (category === "financial") return "financials";
  if (category === "ip") return "ip_technology";
  if (category === "people") return "people";
  return "cross_room";
}

export function fmtCurrency(v, currency) {
  const abs = Math.abs(v);
  const neg = v < 0 ? "-" : "";
  const sym = currency === "EUR" ? "€" : currency === "GBP" ? "£" : "$";
  if (abs >= 1_000_000_000) return `${neg}${sym}${(abs / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${neg}${sym}${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${neg}${sym}${(abs / 1_000).toFixed(0)}K`;
  return `${neg}${sym}${abs.toFixed(0)}`;
}

export function fmtPct(v) {
  return `${(v * 100).toFixed(1)}%`;
}
