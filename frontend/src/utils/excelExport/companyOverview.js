// excelExport/companyOverview.js
import {
  COLORS,
  FONTS,
  applyHeaderStyle,
  applySectionHeaderStyle,
  applyLabelStyle,
  applyValueStyle,
} from "./styles.js";

export function addCompanyOverview(workbook, data) {
  const sheet = workbook.addWorksheet("🏢 Company Overview", {
    views: [{ showGridLines: false }],
  });

  let row = 1;
  const company = data.company_info || {};

  // Title
  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "COMPANY OVERVIEW & PROFILE";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:B${row}`);
  row += 2;

  // Table headers
  const fieldHeaderCell = sheet.getCell(`A${row}`);
  const valueHeaderCell = sheet.getCell(`B${row}`);
  fieldHeaderCell.value = "Field";
  valueHeaderCell.value = "Value";
  applySectionHeaderStyle(fieldHeaderCell);
  applySectionHeaderStyle(valueHeaderCell);
  row++;

  const fields = [
    ["Company Name", company.company_name || "N/A"],
    ["Company ID", company.company_id || "N/A"],
    ["Industry", company.industry || "N/A"],
    ["Secondary Industry", company.secondary_industry || "N/A"],
    ["Business Structure", company.business_structure || "N/A"],
    ["Founded Year", company.founded_year || "N/A"],
    ["Employees", company.employees || "N/A"],
    ["Headquarters", company.headquarters || "N/A"],
    ["Website", company.website || "N/A"],
  ];

  fields.forEach(([label, value], idx) => {
    const labelCell = sheet.getCell(`A${row}`);
    const valueCell = sheet.getCell(`B${row}`);
    labelCell.value = label;
    valueCell.value = value;
    applyLabelStyle(labelCell);
    applyValueStyle(valueCell);

    // Alternate row colors
    if (idx % 2 === 0) {
      labelCell.fill = {
        type: "pattern",
        pattern: "solid",
        fgColor: { argb: `FF${COLORS.lightGray}` },
      };
      valueCell.fill = {
        type: "pattern",
        pattern: "solid",
        fgColor: { argb: `FF${COLORS.lightGray}` },
      };
    }
    row++;
  });
  row++;

  // Investment Thesis
  if (data.investment_thesis) {
    const thesisHeaderCell = sheet.getCell(`A${row}`);
    thesisHeaderCell.value = "💡 INVESTMENT THESIS";
    applySectionHeaderStyle(thesisHeaderCell);
    sheet.mergeCells(`A${row}:B${row}`);
    row += 2;

    const thesisLines = data.investment_thesis.split("\n");
    thesisLines.forEach((line) => {
      const cell = sheet.getCell(`A${row}`);
      cell.value = line;
      cell.font = FONTS.normal;
      cell.alignment = { vertical: "top", horizontal: "left", wrapText: true };
      sheet.mergeCells(`A${row}:B${row}`);
      row++;
    });
  }

  sheet.getColumn(1).width = 30;
  sheet.getColumn(2).width = 70;
}
