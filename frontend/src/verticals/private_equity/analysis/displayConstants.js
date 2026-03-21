import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
} from "lucide-react";

export const CHECKLIST_STATUS = {
  covered: { icon: CheckCircle2, color: "text-green-500", label: "Covered" },
  partial: { icon: AlertTriangle, color: "text-yellow-500", label: "Partial" },
  missing: { icon: XCircle, color: "text-red-500", label: "Missing" },
};

export const SEVERITY_STYLES = {
  high: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800",
  medium: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800",
  low: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-800",
};

export const FINDING_STATUS_STYLES = {
  open: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  resolved: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  dismissed: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500",
};

export const ASSESSMENT_STYLES = {
  below_market: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 border-orange-200 dark:border-orange-800",
  above_market: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800",
  missing: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800",
  non_standard: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 border-purple-200 dark:border-purple-800",
  flagged: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800",
};

export const WORKSTREAM_ORDER = [
  "transaction_legal",
  "commercial",
  "debt_financing",
  "financials",
  "ip_technology",
  "people",
  "cross_room",
];

export const WORKSTREAM_LABELS = {
  transaction_legal: "Transaction & Legal",
  commercial: "Commercial",
  debt_financing: "Debt & Financing",
  financials: "Financials",
  ip_technology: "IP & Technology",
  people: "People",
  cross_room: "Cross-Room",
};

export const COVERAGE_WORKSTREAM_LABELS = {
  commercial: "Commercial",
  esg: "Environmental & ESG",
  financials: "Financials",
  governance: "Governance",
  insurance: "Insurance",
  ip: "IP & Technology",
  legal: "Legal",
  legal_financial: "Debt & Legal",
  people: "People",
  privacy: "Data Privacy",
  regulatory: "Regulatory",
  tax: "Tax",
  transaction_legal: "Transaction & Legal",
};

export const COVERAGE_STATUS_LABELS = {
  gap: "Gap",
  partial: "Partial",
  covered: "Covered",
};

export const ANALYSIS_CATEGORY_LABELS = {
  commercial: "Commercial",
  contract: "Contract",
  debt: "Debt & Financing",
  esg: "Environmental & ESG",
  financial: "Financials",
  financials: "Financials",
  governance: "Governance",
  insurance: "Insurance",
  ip: "IP & Technology",
  legal: "Legal",
  legal_financial: "Debt & Legal",
  missing_clause: "Missing Clause",
  numeric_reconciliation: "Numeric Reconciliation",
  people: "People",
  privacy: "Data Privacy",
  regulatory: "Regulatory",
  spa: "Transaction Terms",
  tax: "Tax",
  transaction_legal: "Transaction & Legal",
};

export const FINDING_STATUS_LABELS = {
  open: "Open",
  resolved: "Resolved",
  dismissed: "Dismissed",
};

export const ASSESSMENT_LABELS = {
  above_market: "Above Market",
  below_market: "Below Market",
  flagged: "Flagged",
  missing: "Missing",
  non_standard: "Non-Standard",
  standard: "Standard",
};

export const DOC_STATUS_CFG = {
  conflict: { bg: "bg-red-100 dark:bg-red-900/30", text: "text-red-600 dark:text-red-400", icon: XCircle },
  warning: { bg: "bg-yellow-100 dark:bg-yellow-900/30", text: "text-yellow-600 dark:text-yellow-400", icon: AlertTriangle },
  ok: { bg: "bg-green-100 dark:bg-green-900/30", text: "text-green-600 dark:text-green-400", icon: CheckCircle2 },
  neutral: { bg: "bg-muted", text: "text-muted-foreground", icon: FileText },
};

export const PLAYBOOK_LABELS = {
  spa_core: "SPA Core Terms",
  change_of_control: "Change of Control & Assignment",
  customer_concentration: "Customer Concentration & Revenue",
  debt_covenants: "Debt & Covenant Analysis",
  ip_ownership: "IP & Technology Ownership",
  employment: "Key Employee & Compensation",
  litigation: "Litigation & Contingent Liability",
  tax_exposure: "Tax Exposure & Structure",
  supplier_contracts: "Material Contracts — Supplier & Vendor",
  regulatory_licensing: "Regulatory & Licensing",
  data_privacy: "Data Privacy & Cybersecurity",
  environmental_esg: "Environmental & ESG",
  insurance_coverage: "Insurance Coverage",
  related_party_transactions: "Related Party Transactions",
  governance_equity: "Governance & Equity Structure",
};

export const CATEGORY_COLORS = {
  spa: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  contract: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  debt: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  ip: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  people: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  commercial: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
};

export const FINDINGS_PAGE_SIZE = 20;
export const DOCS_PAGE_SIZE = 25;
export const CLAUSES_PAGE_SIZE = 20;

export const FINANCIAL_ROW_DEFS = [
  { key: "revenue", label: "Revenue" },
  { key: "ebitda", label: "EBITDA", growthOf: "revenue" },
  { key: "ebitda_margin", label: "EBITDA Margin" },
  { key: "gross_profit", label: "Gross Profit" },
  { key: "net_income", label: "Net Income" },
  { key: "free_cash_flow", label: "Free Cash Flow" },
  { key: "capex", label: "Capex" },
];

export const REVIEW_BADGE = {
  approved: { label: "Approved", className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300" },
  flagged: { label: "Flagged", className: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300" },
  edited: { label: "Edited", className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" },
};
