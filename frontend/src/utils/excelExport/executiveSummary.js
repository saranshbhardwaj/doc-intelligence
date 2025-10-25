// excelExport/executiveSummary.js
import {
  applyHeaderStyle,
  applySectionHeaderStyle,
  applyLabelStyle,
  applyValueStyle,
} from "./styles.js";

export async function addExecutiveSummary(workbook, data, metadata) {
  const sheet = workbook.addWorksheet("📊 Executive Summary", {
    views: [{ showGridLines: false }],
  });

  let row = 1;

  // Title
  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "CONFIDENTIAL INFORMATION MEMORANDUM - EXECUTIVE SUMMARY";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:D${row}`);
  row += 2;

  // Company Info Section
  const companyHeaderCell = sheet.getCell(`A${row}`);
  companyHeaderCell.value = "🏢 COMPANY INFORMATION";
  applySectionHeaderStyle(companyHeaderCell);
  sheet.mergeCells(`A${row}:D${row}`);
  row++;

  const companyFields = [
    ["Company Name:", data.company_info?.company_name || "N/A"],
    ["Industry:", data.company_info?.industry || "N/A"],
    ["Secondary Industry:", data.company_info?.secondary_industry || "N/A"],
    ["Headquarters:", data.company_info?.headquarters || "N/A"],
    ["Employees:", data.company_info?.employees || "N/A"],
    ["Founded:", data.company_info?.founded_year || "N/A"],
  ];

  companyFields.forEach(([label, value]) => {
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    labelCell.value = label;
    valueCell.value = value;
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell);
    row++;
  });
  row++;

  // Transaction Overview
  if (
    data.transaction_details &&
    Object.values(data.transaction_details).some((v) => v != null)
  ) {
    const txHeaderCell = sheet.getCell(`A${row}`);
    txHeaderCell.value = "💰 TRANSACTION OVERVIEW";
    applySectionHeaderStyle(txHeaderCell);
    sheet.mergeCells(`A${row}:D${row}`);
    row++;

    const txFields = [];
    if (data.transaction_details.asking_price) {
      txFields.push(["Asking Price:", data.transaction_details.asking_price]);
    }
    if (data.transaction_details.deal_type) {
      txFields.push(["Deal Type:", data.transaction_details.deal_type]);
    }
    if (data.transaction_details.implied_valuation_hint) {
      txFields.push(["Valuation Multiples:", data.transaction_details.implied_valuation_hint]);
    }

    txFields.forEach(([label, value]) => {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell);
      row++;
    });
    row++;
  }

  // Key Metrics
  const metricsHeaderCell = sheet.getCell(`A${row}`);
  metricsHeaderCell.value = "📈 KEY FINANCIAL METRICS";
  applySectionHeaderStyle(metricsHeaderCell);
  sheet.mergeCells(`A${row}:D${row}`);
  row++;

  const financials = data.financials || {};

  // Latest Revenue
  if (
    financials.revenue_by_year &&
    Object.keys(financials.revenue_by_year).length > 0
  ) {
    const years = Object.keys(financials.revenue_by_year).sort().reverse();
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    const yearCell = sheet.getCell(`C${row}`);
    labelCell.value = "Latest Revenue:";
    valueCell.value = parseFloat(financials.revenue_by_year[years[0]]) || financials.revenue_by_year[years[0]];
    yearCell.value = years[0];
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell, true);
    row++;
  }

  // Latest EBITDA
  if (
    financials.adjusted_ebitda_by_year &&
    Object.keys(financials.adjusted_ebitda_by_year).length > 0
  ) {
    const years = Object.keys(financials.adjusted_ebitda_by_year).sort().reverse();
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    const yearCell = sheet.getCell(`C${row}`);
    labelCell.value = "Latest Adj. EBITDA:";
    valueCell.value = parseFloat(financials.adjusted_ebitda_by_year[years[0]]) || financials.adjusted_ebitda_by_year[years[0]];
    yearCell.value = years[0];
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell, true);
    row++;
  }

  // Key Ratios
  const ratios = data.financial_ratios || {};
  if (ratios.ebitda_margin != null) {
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    labelCell.value = "EBITDA Margin:";
    valueCell.value = ratios.ebitda_margin;
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell);
    row++;
  }
  if (ratios.net_debt_to_ebitda != null) {
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    labelCell.value = "Net Debt / EBITDA:";
    valueCell.value = ratios.net_debt_to_ebitda;
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell);
    row++;
  }
  row++;

  // Growth Metrics
  if (
    data.growth_analysis &&
    Object.values(data.growth_analysis).some((v) => v != null)
  ) {
    const growthHeaderCell = sheet.getCell(`A${row}`);
    growthHeaderCell.value = "📊 GROWTH METRICS";
    applySectionHeaderStyle(growthHeaderCell);
    sheet.mergeCells(`A${row}:D${row}`);
    row++;

    if (data.growth_analysis.historical_cagr != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = "Historical CAGR:";
      valueCell.value = data.growth_analysis.historical_cagr;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell);
      row++;
    }
    if (data.growth_analysis.projected_cagr != null) {
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = "Projected CAGR:";
      valueCell.value = data.growth_analysis.projected_cagr;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell);
      row++;
    }
    row++;
  }

  // Metadata
  const metaHeaderCell = sheet.getCell(`A${row}`);
  metaHeaderCell.value = "📄 DOCUMENT INFORMATION";
  applySectionHeaderStyle(metaHeaderCell);
  sheet.mergeCells(`A${row}:D${row}`);
  row++;

  const metaFields = [
    ["Pages Processed:", metadata?.pages || "N/A"],
    ["Extraction Date:", new Date().toLocaleDateString()],
    ["Request ID:", metadata?.request_id || "N/A"],
  ];

  metaFields.forEach(([label, value]) => {
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    labelCell.value = label;
    valueCell.value = value;
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell);
    row++;
  });

  // Set column widths
  sheet.getColumn(1).width = 35;
  sheet.getColumn(2).width = 30;
  sheet.getColumn(3).width = 20;
  sheet.getColumn(4).width = 20;
}
