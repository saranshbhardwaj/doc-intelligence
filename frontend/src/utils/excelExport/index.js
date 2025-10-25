// excelExport/index.js
// Main entry point for Excel export functionality
import ExcelJS from "exceljs";
import { saveAs } from "file-saver";

// Import sheet generators
import { addExecutiveSummary } from "./executiveSummary.js";
import { addCompanyOverview } from "./companyOverview.js";
import { addFinancialPerformance } from "./financialPerformance.js";
import {
  addBalanceSheetAndRatios,
  addValuationMultiples,
  addCapitalStructure,
  addOperatingMetrics,
  addCustomerMarketAnalysis,
  addStrategicRationale,
  addInvestmentMemo,
  addRiskAnalysis,
  addManagementTeam,
} from "./otherSheets.js";

/**
 * Export CIM data to a beautifully formatted Excel file with charts and formulas
 * Designed for PE/VC analysts
 * Uses ExcelJS (MIT License)
 */
export async function exportToExcel(data, metadata) {
  const workbook = new ExcelJS.Workbook();

  workbook.creator = "Sand Cloud Document Intelligence";
  workbook.created = new Date();
  workbook.modified = new Date();

  // Generate all sheets
  await addExecutiveSummary(workbook, data, metadata);
  addCompanyOverview(workbook, data);
  addFinancialPerformance(workbook, data);
  addBalanceSheetAndRatios(workbook, data);
  addValuationMultiples(workbook, data);
  addCapitalStructure(workbook, data);
  addOperatingMetrics(workbook, data);
  addCustomerMarketAnalysis(workbook, data);
  addStrategicRationale(workbook, data);
  addInvestmentMemo(workbook, data);
  addRiskAnalysis(workbook, data);
  addManagementTeam(workbook, data);

  // Generate filename with company name and date
  const companyName = data.company_info?.company_name || "Company";
  const dateStr = new Date().toISOString().split("T")[0];
  const filename = sanitizeFilename(companyName) + `_CIM_Analysis_${dateStr}.xlsx`;

  // Write the file
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  saveAs(blob, filename);
}

function sanitizeFilename(name) {
  return name.replace(/[^a-z0-9]/gi, "_").substring(0, 50);
}
