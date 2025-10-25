// excelExport/otherSheets.js
// Consolidated sheets: Balance Sheet, Ratios, Valuation, Capital, Operating, Customer, Strategic, Investment, Risk, Management
import {
  COLORS,
  FONTS,
  applyHeaderStyle,
  applySectionHeaderStyle,
  applyLabelStyle,
  applyValueStyle,
  applyAlternateRowColor,
} from "./styles.js";

export function addBalanceSheetAndRatios(workbook, data) {
  const sheet = workbook.addWorksheet("📊 Balance Sheet & Ratios", {
    views: [{ showGridLines: false }],
  });

  const balance = data.balance_sheet || {};
  const ratios = data.financial_ratios || {};
  let row = 1;

  // Title
  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "BALANCE SHEET";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  if (balance.most_recent_year) {
    const yearCell = sheet.getCell(`A${row}`);
    yearCell.value = `Most Recent Year: ${balance.most_recent_year}`;
    yearCell.font = FONTS.label;
    sheet.mergeCells(`A${row}:B${row}`);
    row += 2;
  }

  // Balance Sheet Table
  const itemHeaderCell = sheet.getCell(`A${row}`);
  const amountHeaderCell = sheet.getCell(`B${row}`);
  itemHeaderCell.value = "Item";
  amountHeaderCell.value = "Amount";
  applySectionHeaderStyle(itemHeaderCell);
  applySectionHeaderStyle(amountHeaderCell);
  row++;

  // Assets Section
  const assetsHeaderCell = sheet.getCell(`A${row}`);
  assetsHeaderCell.value = "ASSETS";
  applyLabelStyle(assetsHeaderCell);
  assetsHeaderCell.font = { ...FONTS.label, size: 12, color: { argb: `FF${COLORS.primary}` } };
  row++;

  const assetItems = [
    ["Total Assets", balance.total_assets],
    ["  Current Assets", balance.current_assets],
    ["  Fixed Assets", balance.fixed_assets],
  ];

  assetItems.forEach(([label, value]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = parseFloat(value) || value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell, true);
      row++;
    }
  });

  row++;

  // Liabilities & Equity Section
  const liabHeaderCell = sheet.getCell(`A${row}`);
  liabHeaderCell.value = "LIABILITIES & EQUITY";
  applyLabelStyle(liabHeaderCell);
  liabHeaderCell.font = { ...FONTS.label, size: 12, color: { argb: `FF${COLORS.primary}` } };
  row++;

  const liabItems = [
    ["Total Liabilities", balance.total_liabilities],
    ["  Current Liabilities", balance.current_liabilities],
    ["  Long-Term Debt", balance.long_term_debt],
    ["Stockholders Equity", balance.stockholders_equity],
    ["Working Capital", balance.working_capital],
  ];

  liabItems.forEach(([label, value]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = parseFloat(value) || value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell, true);
      row++;
    }
  });

  row += 3;

  // Financial Ratios Section
  const ratiosHeaderCell = sheet.getCell(`A${row}`);
  ratiosHeaderCell.value = "FINANCIAL RATIOS";
  applyHeaderStyle(ratiosHeaderCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  // Key PE Metrics
  const peHeaderCell = sheet.getCell(`A${row}`);
  const peValueHeaderCell = sheet.getCell(`B${row}`);
  peHeaderCell.value = "KEY PE METRICS";
  peValueHeaderCell.value = "Value";
  applySectionHeaderStyle(peHeaderCell);
  applySectionHeaderStyle(peValueHeaderCell);
  row++;

  const peMetrics = [
    ["EBITDA Margin", ratios.ebitda_margin, false],
    ["Net Debt / EBITDA", ratios.net_debt_to_ebitda, false],
    ["CapEx % of Revenue", ratios.capex_pct_revenue, true],
    ["Return on Equity", ratios.return_on_equity, true],
  ];

  peMetrics.forEach(([label, value, isPct]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = parseFloat(value) || value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell, false, isPct);
      row++;
    }
  });

  row++;

  // Liquidity Ratios
  const liqHeaderCell = sheet.getCell(`A${row}`);
  const liqValueHeaderCell = sheet.getCell(`B${row}`);
  liqHeaderCell.value = "LIQUIDITY RATIOS";
  liqValueHeaderCell.value = "Value";
  applySectionHeaderStyle(liqHeaderCell);
  applySectionHeaderStyle(liqValueHeaderCell);
  row++;

  const liqRatios = [
    ["Current Ratio", ratios.current_ratio],
    ["Quick Ratio", ratios.quick_ratio],
  ];

  liqRatios.forEach(([label, value]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = parseFloat(value) || value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell);
      row++;
    }
  });

  sheet.getColumn(1).width = 35;
  sheet.getColumn(2).width = 22;
}

export function addValuationMultiples(workbook, data) {
  const sheet = workbook.addWorksheet("💎 Valuation Multiples", {
    views: [{ showGridLines: false }],
  });

  const multiples = data.valuation_multiples || {};
  let row = 1;

  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "VALUATION MULTIPLES";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  if (!Object.values(multiples).some((v) => v != null)) {
    const noDataCell = sheet.getCell(`A${row}`);
    noDataCell.value = "No valuation multiples data available";
    noDataCell.font = FONTS.normal;
    return;
  }

  const multipleHeaderCell = sheet.getCell(`A${row}`);
  const valueHeaderCell = sheet.getCell(`B${row}`);
  multipleHeaderCell.value = "Multiple";
  valueHeaderCell.value = "Value";
  applySectionHeaderStyle(multipleHeaderCell);
  applySectionHeaderStyle(valueHeaderCell);
  row++;

  const multiplesData = [
    ["Asking EV / EBITDA", multiples.asking_ev_ebitda, "x"],
    ["Asking EV / Revenue", multiples.asking_ev_revenue, "x"],
    ["Estimated Exit EV / EBITDA", multiples.exit_ev_ebitda_estimate, "x"],
    ["Comparable Multiples Range", multiples.comparable_multiples_range, ""],
  ];

  multiplesData.forEach(([label, value, suffix]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;

      if (typeof value === "number") {
        valueCell.value = value;
        if (suffix === "x") {
          valueCell.numFmt = "0.0\"x\"";
        }
      } else {
        valueCell.value = value;
      }

      applyLabelStyle(labelCell);
      applyValueStyle(valueCell);
      row++;
    }
  });

  sheet.getColumn(1).width = 38;
  sheet.getColumn(2).width = 22;
}

export function addCapitalStructure(workbook, data) {
  const sheet = workbook.addWorksheet("🏦 Capital Structure", {
    views: [{ showGridLines: false }],
  });

  const capital = data.capital_structure || {};
  let row = 1;

  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "CAPITAL STRUCTURE";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  if (!Object.values(capital).some((v) => v != null)) {
    const noDataCell = sheet.getCell(`A${row}`);
    noDataCell.value = "No capital structure data available";
    noDataCell.font = FONTS.normal;
    return;
  }

  const itemHeaderCell = sheet.getCell(`A${row}`);
  const valueHeaderCell = sheet.getCell(`B${row}`);
  itemHeaderCell.value = "Item";
  valueHeaderCell.value = "Value";
  applySectionHeaderStyle(itemHeaderCell);
  applySectionHeaderStyle(valueHeaderCell);
  row++;

  const capitalItems = [
    ["Existing Debt", capital.existing_debt, true],
    ["Debt / EBITDA", capital.debt_to_ebitda, false, "x"],
    ["Proposed Leverage", capital.proposed_leverage, false, "x"],
    ["Estimated Equity Contribution", capital.equity_contribution_estimate, true],
  ];

  capitalItems.forEach(([label, value, isCurrency, suffix]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;

      if (typeof value === "number") {
        valueCell.value = value;
        if (suffix === "x") {
          valueCell.numFmt = "0.0\"x\"";
        } else if (isCurrency) {
          valueCell.numFmt = "$#,##0.00";
        }
      } else {
        valueCell.value = value;
      }

      applyLabelStyle(labelCell);
      applyValueStyle(valueCell, isCurrency);
      row++;
    }
  });

  sheet.getColumn(1).width = 38;
  sheet.getColumn(2).width = 28;
}

export function addOperatingMetrics(workbook, data) {
  const sheet = workbook.addWorksheet("⚙️ Operating Metrics", {
    views: [{ showGridLines: false }],
  });

  const metrics = data.operating_metrics || {};
  let row = 1;

  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "OPERATING METRICS";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:H${row}`);
  row += 2;

  if (!Object.values(metrics).some((v) => v != null)) {
    const noDataCell = sheet.getCell(`A${row}`);
    noDataCell.value = "No operating metrics data available";
    noDataCell.font = FONTS.normal;
    return;
  }

  const kpiHeaderCell = sheet.getCell(`A${row}`);
  kpiHeaderCell.value = "KEY OPERATING KPIS";
  applySectionHeaderStyle(kpiHeaderCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row++;

  const metricHeaderCell = sheet.getCell(`A${row}`);
  const valueHeaderCell = sheet.getCell(`B${row}`);
  metricHeaderCell.value = "Metric";
  valueHeaderCell.value = "Value";
  applySectionHeaderStyle(metricHeaderCell);
  applySectionHeaderStyle(valueHeaderCell);
  row++;

  if (metrics.working_capital_pct_revenue != null) {
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    labelCell.value = "Working Capital % of Revenue";
    valueCell.value = metrics.working_capital_pct_revenue;
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell, false, true);
    row++;
  }

  if (metrics.pricing_power) {
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    labelCell.value = "Pricing Power";
    valueCell.value = metrics.pricing_power;
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell);
    row++;
  }

  row += 2;

  // Free Cash Flow by Year
  if (metrics.fcf_by_year && Object.keys(metrics.fcf_by_year).length > 0) {
    const fcfHeaderCell = sheet.getCell(`A${row}`);
    fcfHeaderCell.value = "FREE CASH FLOW BY YEAR";
    applySectionHeaderStyle(fcfHeaderCell);
    sheet.mergeCells(`A${row}:H${row}`);
    row++;

    const fcfYears = Object.keys(metrics.fcf_by_year).sort((a, b) => {
      const yearA = parseInt(a.replace("projected_", ""));
      const yearB = parseInt(b.replace("projected_", ""));
      return yearA - yearB;
    });

    const yearHeaderCell = sheet.getCell(`A${row}`);
    yearHeaderCell.value = "Year";
    applySectionHeaderStyle(yearHeaderCell);

    fcfYears.forEach((year, idx) => {
      const cell = sheet.getCell(row, idx + 2);
      cell.value =
        year.replace("projected_", "") +
        (year.startsWith("projected_") ? " (P)" : "");
      applySectionHeaderStyle(cell);
    });
    row++;

    const fcfLabelCell = sheet.getCell(`A${row}`);
    fcfLabelCell.value = "FCF";
    applyLabelStyle(fcfLabelCell);

    fcfYears.forEach((year, idx) => {
      const valueCell = sheet.getCell(row, idx + 2);
      const value = metrics.fcf_by_year[year];
      valueCell.value = parseFloat(value) || value || "";
      applyValueStyle(valueCell, true);
    });
    row += 2;
  }

  // CapEx by Year
  if (metrics.capex_by_year && Object.keys(metrics.capex_by_year).length > 0) {
    const capexHeaderCell = sheet.getCell(`A${row}`);
    capexHeaderCell.value = "CAPITAL EXPENDITURES BY YEAR";
    applySectionHeaderStyle(capexHeaderCell);
    sheet.mergeCells(`A${row}:H${row}`);
    row++;

    const capexYears = Object.keys(metrics.capex_by_year).sort((a, b) => {
      const yearA = parseInt(a.replace("projected_", ""));
      const yearB = parseInt(b.replace("projected_", ""));
      return yearA - yearB;
    });

    const yearHeaderCell = sheet.getCell(`A${row}`);
    yearHeaderCell.value = "Year";
    applySectionHeaderStyle(yearHeaderCell);

    capexYears.forEach((year, idx) => {
      const cell = sheet.getCell(row, idx + 2);
      cell.value =
        year.replace("projected_", "") +
        (year.startsWith("projected_") ? " (P)" : "");
      applySectionHeaderStyle(cell);
    });
    row++;

    const capexLabelCell = sheet.getCell(`A${row}`);
    capexLabelCell.value = "CapEx";
    applyLabelStyle(capexLabelCell);

    capexYears.forEach((year, idx) => {
      const valueCell = sheet.getCell(row, idx + 2);
      const value = metrics.capex_by_year[year];
      valueCell.value = parseFloat(value) || value || "";
      applyValueStyle(valueCell, true);
    });
    row += 2;
  }

  sheet.getColumn(1).width = 35;
  for (let i = 2; i <= 8; i++) {
    sheet.getColumn(i).width = 18;
  }
}

export function addCustomerMarketAnalysis(workbook, data) {
  const sheet = workbook.addWorksheet("👥 Customer & Market", {
    views: [{ showGridLines: false }],
  });

  const customers = data.customers || {};
  const market = data.market || {};
  let row = 1;

  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "CUSTOMER METRICS";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  const metricHeaderCell = sheet.getCell(`A${row}`);
  const valueHeaderCell = sheet.getCell(`B${row}`);
  metricHeaderCell.value = "Metric";
  valueHeaderCell.value = "Value";
  applySectionHeaderStyle(metricHeaderCell);
  applySectionHeaderStyle(valueHeaderCell);
  row++;

  const customerMetrics = [
    ["Total Customers", customers.total_count],
    ["Top Customer Concentration", customers.top_customer_concentration],
    ["Top Customer %", customers.top_customer_concentration_pct, true],
    ["Retention Rate", customers.customer_retention_rate],
    ["Recurring Revenue %", customers.recurring_revenue_pct, true],
  ];

  customerMetrics.forEach(([label, value, isPct]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = parseFloat(value) || value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell, false, isPct);
      row++;
    }
  });

  row += 2;

  // Revenue Mix by Segment
  if (
    customers.revenue_mix_by_segment &&
    Object.keys(customers.revenue_mix_by_segment).length > 0
  ) {
    const revMixHeaderCell = sheet.getCell(`A${row}`);
    revMixHeaderCell.value = "REVENUE MIX BY SEGMENT";
    applySectionHeaderStyle(revMixHeaderCell);
    sheet.mergeCells(`A${row}:B${row}`);
    row++;

    const segHeaderCell = sheet.getCell(`A${row}`);
    const pctHeaderCell = sheet.getCell(`B${row}`);
    segHeaderCell.value = "Segment";
    pctHeaderCell.value = "Percentage";
    applySectionHeaderStyle(segHeaderCell);
    applySectionHeaderStyle(pctHeaderCell);
    row++;

    Object.entries(customers.revenue_mix_by_segment).forEach(([segment, pct]) => {
      const segCell = sheet.getCell(`A${row}`);
      const pctCell = sheet.getCell(`B${row}`);
      segCell.value = segment;
      pctCell.value = parseFloat(pct) || pct;
      applyLabelStyle(segCell);
      applyValueStyle(pctCell);
      row++;
    });
    row += 2;
  }

  // Notable Customers
  if (
    Array.isArray(customers.notable_customers) &&
    customers.notable_customers.length > 0
  ) {
    const notableHeaderCell = sheet.getCell(`A${row}`);
    notableHeaderCell.value = "NOTABLE CUSTOMERS";
    applySectionHeaderStyle(notableHeaderCell);
    sheet.mergeCells(`A${row}:B${row}`);
    row++;

    customers.notable_customers.forEach((customer) => {
      const cell = sheet.getCell(`A${row}`);
      cell.value = customer;
      cell.font = FONTS.normal;
      sheet.mergeCells(`A${row}:B${row}`);
      row++;
    });
    row += 2;
  }

  // Market Analysis
  const marketHeaderCell = sheet.getCell(`A${row}`);
  marketHeaderCell.value = "MARKET ANALYSIS";
  applyHeaderStyle(marketHeaderCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  const mktMetricHeaderCell = sheet.getCell(`A${row}`);
  const mktValueHeaderCell = sheet.getCell(`B${row}`);
  mktMetricHeaderCell.value = "Metric";
  mktValueHeaderCell.value = "Value";
  applySectionHeaderStyle(mktMetricHeaderCell);
  applySectionHeaderStyle(mktValueHeaderCell);
  row++;

  const marketMetrics = [
    ["Market Size", market.market_size],
    ["Market Size (Estimate)", market.market_size_estimate],
    ["Market Growth Rate", market.market_growth_rate],
    ["Competitive Position", market.competitive_position],
    ["Market Share", market.market_share],
  ];

  marketMetrics.forEach(([label, value]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell);
      row++;
    }
  });

  sheet.getColumn(1).width = 35;
  sheet.getColumn(2).width = 45;
}

export function addStrategicRationale(workbook, data) {
  const sheet = workbook.addWorksheet("🎯 Strategic Rationale", {
    views: [{ showGridLines: false }],
  });

  const rationale = data.strategic_rationale || {};
  let row = 1;

  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "STRATEGIC RATIONALE & DEAL THESIS";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  if (!Object.values(rationale).some((v) => v != null)) {
    const noDataCell = sheet.getCell(`A${row}`);
    noDataCell.value = "No strategic rationale data available";
    noDataCell.font = FONTS.normal;
    return;
  }

  // Deal Thesis
  if (rationale.deal_thesis) {
    const thesisHeaderCell = sheet.getCell(`A${row}`);
    thesisHeaderCell.value = "DEAL THESIS";
    applySectionHeaderStyle(thesisHeaderCell);
    sheet.mergeCells(`A${row}:B${row}`);
    row += 2;

    const thesisLines = rationale.deal_thesis.split("\n");
    thesisLines.forEach((line) => {
      const cell = sheet.getCell(`A${row}`);
      cell.value = line;
      cell.font = FONTS.normal;
      cell.alignment = { vertical: "top", horizontal: "left", wrapText: true };
      sheet.mergeCells(`A${row}:B${row}`);
      row++;
    });
    row += 2;
  }

  // Value Creation Plan
  if (rationale.value_creation_plan) {
    const vcpHeaderCell = sheet.getCell(`A${row}`);
    vcpHeaderCell.value = "VALUE CREATION PLAN";
    applySectionHeaderStyle(vcpHeaderCell);
    sheet.mergeCells(`A${row}:B${row}`);
    row += 2;

    const vcpLines = rationale.value_creation_plan.split("\n");
    vcpLines.forEach((line) => {
      const cell = sheet.getCell(`A${row}`);
      cell.value = line;
      cell.font = FONTS.normal;
      cell.alignment = { vertical: "top", horizontal: "left", wrapText: true };
      sheet.mergeCells(`A${row}:B${row}`);
      row++;
    });
    row += 2;
  }

  sheet.getColumn(1).width = 5;
  sheet.getColumn(2).width = 90;
}

export function addInvestmentMemo(workbook, data) {
  const sheet = workbook.addWorksheet("📝 Investment Memo", {
    views: [{ showGridLines: false }],
  });

  const tx = data.transaction_details || {};
  const growth = data.growth_analysis || {};
  const derived = data.derived_metrics || {};
  let row = 1;

  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "INVESTMENT MEMORANDUM";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  // Transaction Details
  const txHeaderCell = sheet.getCell(`A${row}`);
  txHeaderCell.value = "TRANSACTION DETAILS";
  applySectionHeaderStyle(txHeaderCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row++;

  const fieldHeaderCell = sheet.getCell(`A${row}`);
  const valueHeaderCell = sheet.getCell(`B${row}`);
  fieldHeaderCell.value = "Field";
  valueHeaderCell.value = "Value";
  applySectionHeaderStyle(fieldHeaderCell);
  applySectionHeaderStyle(valueHeaderCell);
  row++;

  const txFields = [
    ["Deal Type", tx.deal_type],
    ["Asking Price", tx.asking_price],
    ["Valuation Multiples", tx.implied_valuation_hint],
    ["Assets for Sale", tx.assets_for_sale],
    ["Auction Deadline", tx.auction_deadline],
  ];

  txFields.forEach(([label, value]) => {
    if (value != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell);
      row++;
    }
  });

  sheet.getColumn(1).width = 35;
  sheet.getColumn(2).width = 65;
}

export function addRiskAnalysis(workbook, data) {
  const sheet = workbook.addWorksheet("⚠️ Risk Analysis", {
    views: [{ showGridLines: false }],
  });

  let row = 1;

  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "RISK ANALYSIS";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:F${row}`);
  row += 2;

  if (!Array.isArray(data.key_risks) || data.key_risks.length === 0) {
    const noDataCell = sheet.getCell(`A${row}`);
    noDataCell.value = "No risks identified";
    noDataCell.font = FONTS.normal;
    return;
  }

  const headers = ["#", "Severity", "Risk", "Description", "Mitigation", "Source"];
  headers.forEach((header, idx) => {
    const cell = sheet.getCell(row, idx + 1);
    cell.value = header;
    applySectionHeaderStyle(cell);
  });
  row++;

  data.key_risks.forEach((risk, index) => {
    const rowData = typeof risk === "object"
      ? [
          index + 1,
          risk.severity || "N/A",
          risk.risk || "N/A",
          risk.description || "",
          risk.mitigation || "",
          risk.inferred ? "Inferred" : "Explicit",
        ]
      : [index + 1, "", risk, "", "", ""];

    rowData.forEach((value, colIdx) => {
      const cell = sheet.getCell(row, colIdx + 1);
      cell.value = value;
      cell.font = FONTS.normal;
      cell.alignment = { vertical: "top", horizontal: "left", wrapText: true };

      // Color code severity
      if (colIdx === 1 && typeof risk === "object") {
        const severity = risk.severity?.toLowerCase();
        if (severity === "high" || severity === "critical") {
          cell.font = { ...FONTS.normal, bold: true, color: { argb: `FF${COLORS.danger}` } };
        } else if (severity === "medium" || severity === "moderate") {
          cell.font = { ...FONTS.normal, bold: true, color: { argb: `FF${COLORS.warning}` } };
        } else if (severity === "low") {
          cell.font = { ...FONTS.normal, bold: true, color: { argb: `FF${COLORS.success}` } };
        }
      }

      applyAlternateRowColor(cell, index);
    });
    row++;
  });

  sheet.getColumn(1).width = 5;
  sheet.getColumn(2).width = 13;
  sheet.getColumn(3).width = 28;
  sheet.getColumn(4).width = 45;
  sheet.getColumn(5).width = 45;
  sheet.getColumn(6).width = 13;
}

export function addManagementTeam(workbook, data) {
  const sheet = workbook.addWorksheet("👔 Management Team", {
    views: [{ showGridLines: false }],
  });

  let row = 1;

  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "MANAGEMENT TEAM";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:D${row}`);
  row += 2;

  if (!Array.isArray(data.management_team) || data.management_team.length === 0) {
    const noDataCell = sheet.getCell(`A${row}`);
    noDataCell.value = "No management team information available";
    noDataCell.font = FONTS.normal;
    return;
  }

  const headers = ["Name", "Title", "Background", "LinkedIn"];
  headers.forEach((header, idx) => {
    const cell = sheet.getCell(row, idx + 1);
    cell.value = header;
    applySectionHeaderStyle(cell);
  });
  row++;

  data.management_team.forEach((member, idx) => {
    const rowData = [
      member.name || "N/A",
      member.title || "N/A",
      member.background || "",
      member.linkedin || "",
    ];

    rowData.forEach((value, colIdx) => {
      const cell = sheet.getCell(row, colIdx + 1);

      // LinkedIn as hyperlink
      if (colIdx === 3 && value && value.startsWith("http")) {
        cell.value = {
          text: value,
          hyperlink: value,
        };
        cell.font = { ...FONTS.normal, color: { argb: `FF${COLORS.primary}` }, underline: true };
      } else {
        cell.value = value;
        cell.font = FONTS.normal;
      }

      cell.alignment = { vertical: "top", horizontal: "left", wrapText: true };
      applyAlternateRowColor(cell, idx);
    });
    row++;
  });

  sheet.getColumn(1).width = 28;
  sheet.getColumn(2).width = 35;
  sheet.getColumn(3).width = 55;
  sheet.getColumn(4).width = 45;
}
