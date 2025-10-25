// excelExport/financialPerformance.js
import {
  COLORS,
  FONTS,
  applyHeaderStyle,
  applySectionHeaderStyle,
  applyLabelStyle,
  applyValueStyle,
} from "./styles.js";

export function addFinancialPerformance(workbook, data) {
  const sheet = workbook.addWorksheet("💵 Financials", {
    views: [{ showGridLines: false }],
  });

  const financials = data.financials || {};
  let row = 1;

  // Title
  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "FINANCIAL PERFORMANCE - HISTORICAL & PROJECTED";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:H${row}`);
  row += 2;

  // Currency info
  const currencyCell = sheet.getCell(`A${row}`);
  currencyCell.value = `Currency: ${
    financials.currency || "USD"
  }  |  Fiscal Year End: ${financials.fiscal_year_end || "N/A"}`;
  currencyCell.font = FONTS.label;
  sheet.mergeCells(`A${row}:H${row}`);
  row += 2;

  // Get all years
  const allYears = new Set();
  [
    "revenue_by_year",
    "ebitda_by_year",
    "adjusted_ebitda_by_year",
    "net_income_by_year",
    "gross_margin_by_year",
  ].forEach((key) => {
    if (financials[key]) {
      Object.keys(financials[key]).forEach((year) => allYears.add(year));
    }
  });

  const sortedYears = Array.from(allYears).sort((a, b) => {
    const yearA = parseInt(a.replace("projected_", ""));
    const yearB = parseInt(b.replace("projected_", ""));
    return yearA - yearB;
  });

  if (sortedYears.length > 0) {
    // Headers
    const metricHeaderCell = sheet.getCell(`A${row}`);
    metricHeaderCell.value = "Metric";
    applySectionHeaderStyle(metricHeaderCell);

    sortedYears.forEach((year, idx) => {
      const yearCell = sheet.getCell(row, idx + 2);
      yearCell.value =
        year.replace("projected_", "") +
        (year.startsWith("projected_") ? " (P)" : "");
      applySectionHeaderStyle(yearCell);
    });
    row++;

    const revenueRow = row;
    const adjEbitdaRow = row + 2;

    // Revenue
    if (financials.revenue_by_year) {
      const labelCell = sheet.getCell(`A${row}`);
      labelCell.value = "Revenue";
      applyLabelStyle(labelCell);

      sortedYears.forEach((year, idx) => {
        const valueCell = sheet.getCell(row, idx + 2);
        const value = financials.revenue_by_year[year];
        valueCell.value = parseFloat(value) || value || "";
        applyValueStyle(valueCell, true);
      });
      row++;
    }

    // EBITDA
    if (financials.ebitda_by_year) {
      const labelCell = sheet.getCell(`A${row}`);
      labelCell.value = "EBITDA";
      applyLabelStyle(labelCell);

      sortedYears.forEach((year, idx) => {
        const valueCell = sheet.getCell(row, idx + 2);
        const value = financials.ebitda_by_year[year];
        valueCell.value = parseFloat(value) || value || "";
        applyValueStyle(valueCell, true);
      });
      row++;
    }

    // Adjusted EBITDA
    if (financials.adjusted_ebitda_by_year) {
      const labelCell = sheet.getCell(`A${row}`);
      labelCell.value = "Adjusted EBITDA";
      applyLabelStyle(labelCell);

      sortedYears.forEach((year, idx) => {
        const valueCell = sheet.getCell(row, idx + 2);
        const value = financials.adjusted_ebitda_by_year[year];
        valueCell.value = parseFloat(value) || value || "";
        applyValueStyle(valueCell, true);
      });
      row++;
    }

    // Net Income
    if (financials.net_income_by_year) {
      const labelCell = sheet.getCell(`A${row}`);
      labelCell.value = "Net Income";
      applyLabelStyle(labelCell);

      sortedYears.forEach((year, idx) => {
        const valueCell = sheet.getCell(row, idx + 2);
        const value = financials.net_income_by_year[year];
        valueCell.value = parseFloat(value) || value || "";
        applyValueStyle(valueCell, true);
      });
      row++;
    }

    // Gross Margin
    if (financials.gross_margin_by_year) {
      const labelCell = sheet.getCell(`A${row}`);
      labelCell.value = "Gross Margin";
      applyLabelStyle(labelCell);

      sortedYears.forEach((year, idx) => {
        const valueCell = sheet.getCell(row, idx + 2);
        const val = financials.gross_margin_by_year[year];
        valueCell.value = val != null ? parseFloat(val) : "";
        applyValueStyle(valueCell, false, true);
      });
      row++;
    }

    // Add EBITDA Margin calculation (formula)
    if (financials.revenue_by_year && financials.adjusted_ebitda_by_year) {
      row++;
      const labelCell = sheet.getCell(`A${row}`);
      labelCell.value = "EBITDA Margin (Calculated)";
      applyLabelStyle(labelCell);
      labelCell.font = {
        ...FONTS.label,
        italic: true,
        color: { argb: `FF${COLORS.primary}` },
      };

      sortedYears.forEach((year, idx) => {
        const col = idx + 2;
        const valueCell = sheet.getCell(row, col);
        const colLetter = String.fromCharCode(65 + col - 1);

        // Formula: EBITDA / Revenue
        if (
          financials.revenue_by_year[year] &&
          financials.adjusted_ebitda_by_year[year]
        ) {
          valueCell.value = {
            formula: `${colLetter}${adjEbitdaRow}/${colLetter}${revenueRow}`,
          };
          applyValueStyle(valueCell, false, true);
        }
      });
      row++;
    }
  }

  row += 2;

  // Other Metrics
  if (
    financials.other_metrics &&
    Object.keys(financials.other_metrics).length > 0
  ) {
    const otherHeaderCell = sheet.getCell(`A${row}`);
    otherHeaderCell.value = "OTHER FINANCIAL METRICS";
    applySectionHeaderStyle(otherHeaderCell);
    sheet.mergeCells(`A${row}:B${row}`);
    row++;

    const metricHeaderCell = sheet.getCell(`A${row}`);
    const valueHeaderCell = sheet.getCell(`B${row}`);
    metricHeaderCell.value = "Metric";
    valueHeaderCell.value = "Value";
    applySectionHeaderStyle(metricHeaderCell);
    applySectionHeaderStyle(valueHeaderCell);
    row++;

    Object.entries(financials.other_metrics).forEach(([key, value]) => {
      const label = key
        .replace(/_/g, " ")
        .replace(/\b\w/g, (l) => l.toUpperCase());
      const labelCell = sheet.getCell(`A${row}`);
      const valueCell = sheet.getCell(`B${row}`);
      labelCell.value = label;
      valueCell.value = value;
      applyLabelStyle(labelCell);
      applyValueStyle(valueCell);
      row++;
    });
  }

  // Set column widths
  sheet.getColumn(1).width = 28;
  sortedYears.forEach((_, idx) => {
    sheet.getColumn(idx + 2).width = 18;
  });
}
