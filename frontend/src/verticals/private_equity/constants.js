/**
 * Shared constants for PE diligence UI
 */

export const DOC_TYPE_LABELS = {
  offering_memorandum:  "CIM / OM",
  financial_statement:  "Financials",
  purchase_agreement:   "SPA",
  merger_agreement:     "Merger Agreement",
  qoe_report:           "QoE Report",
  customer_contract:    "Customer Contract",
  employment_agreement: "Employment",
  ip_license:           "IP License",
  vendor_contract:      "Vendor Contract",
  nda:                  "NDA",
  legal_contract:       "Contract",
  amendment:            "Amendment",
  other:                "Other",
};

/**
 * Doc type badge colors — uses `dt-*` design tokens from tailwind.config.js.
 * To change colors: edit CSS variables in index.css (--dt-X and --dt-X-fg),
 * not this file.
 */
export const DOC_TYPE_COLORS = {
  offering_memorandum:  "bg-dt-cim text-dt-cim-foreground",
  financial_statement:  "bg-dt-financial text-dt-financial-foreground",
  purchase_agreement:   "bg-dt-spa text-dt-spa-foreground",
  merger_agreement:     "bg-dt-merger text-dt-merger-foreground",
  qoe_report:           "bg-dt-qoe text-dt-qoe-foreground",
  customer_contract:    "bg-dt-customer text-dt-customer-foreground",
  employment_agreement: "bg-dt-employment text-dt-employment-foreground",
  ip_license:           "bg-dt-ip-license text-dt-ip-license-foreground",
  vendor_contract:      "bg-dt-vendor text-dt-vendor-foreground",
  nda:                  "bg-dt-nda text-dt-nda-foreground",
  legal_contract:       "bg-dt-legal text-dt-legal-foreground",
  amendment:            "bg-dt-amendment text-dt-amendment-foreground",
  other:                "bg-dt-other text-dt-other-foreground",
};

/**
 * Minimal markdown to HTML renderer
 * Used for rendering finding descriptions and analysis content
 */
export function mdToHtml(md) {
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, "<h3 class='font-bold mt-3 mb-1'>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2 class='font-bold text-base mt-4 mb-1'>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1 class='font-bold text-lg mt-4 mb-2'>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^- (.+)$/gm, "<li class='ml-4 list-disc'>$1</li>")
    .replace(/\n\n/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
}
