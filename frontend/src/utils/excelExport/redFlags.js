// excelExport/redFlags.js
// Red Flags sheet with color-coded severity indicators
import {
  COLORS,
  FONTS,
  applyHeaderStyle,
  applySectionHeaderStyle,
  applyLabelStyle,
  applyValueStyle,
} from "./styles.js";

export function addRedFlags(workbook, data) {
  const sheet = workbook.addWorksheet("🚩 Red Flags", {
    views: [{ showGridLines: false }],
  });

  const redFlags = data.red_flags || [];
  let row = 1;

  // Title
  const titleCell = sheet.getCell(`A${row}`);
  titleCell.value = "AUTOMATED RED FLAGS ANALYSIS";
  applyHeaderStyle(titleCell);
  sheet.mergeCells(`A${row}:D${row}`);
  row += 2;

  if (redFlags.length === 0) {
    const noFlagsCell = sheet.getCell(`A${row}`);
    noFlagsCell.value = "✅ No significant red flags detected";
    noFlagsCell.font = { ...FONTS.label, color: { argb: "FF059669" }, size: 12 };
    sheet.mergeCells(`A${row}:D${row}`);

    // Set column widths
    sheet.getColumn(1).width = 50;
    return;
  }

  // Summary Stats
  const counts = redFlags.reduce(
    (acc, flag) => {
      if (flag.severity === "High") acc.high++;
      else if (flag.severity === "Medium") acc.medium++;
      else acc.low++;
      return acc;
    },
    { high: 0, medium: 0, low: 0 }
  );

  const summaryCell = sheet.getCell(`A${row}`);
  summaryCell.value = `Total Flags: ${redFlags.length} | High: ${counts.high} | Medium: ${counts.medium} | Low: ${counts.low}`;
  summaryCell.font = { ...FONTS.label, bold: true, size: 11 };
  summaryCell.fill = {
    type: "pattern",
    pattern: "solid",
    fgColor: { argb: "FFFEF2F2" },
  };
  summaryCell.border = {
    top: { style: "thin", color: { argb: "FFDC2626" } },
    bottom: { style: "thin", color: { argb: "FFDC2626" } },
    left: { style: "thin", color: { argb: "FFDC2626" } },
    right: { style: "thin", color: { argb: "FFDC2626" } },
  };
  sheet.mergeCells(`A${row}:D${row}`);
  row += 2;

  const noteCell = sheet.getCell(`A${row}`);
  noteCell.value = "These flags are automatically detected based on quantitative rules and industry benchmarks.";
  noteCell.font = { ...FONTS.body, italic: true, size: 9, color: { argb: "FF6B7280" } };
  sheet.mergeCells(`A${row}:D${row}`);
  row += 2;

  // Group flags by category
  const byCategory = redFlags.reduce((acc, flag) => {
    const cat = flag.category || "Other";
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(flag);
    return acc;
  }, {});

  // Render each category
  Object.entries(byCategory).forEach(([category, flags]) => {
    // Category Header
    const catHeaderCell = sheet.getCell(`A${row}`);
    catHeaderCell.value = `${category.toUpperCase()} RISKS`;
    catHeaderCell.font = { ...FONTS.sectionHeader, size: 11 };
    catHeaderCell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: "FFF3F4F6" },
    };
    sheet.mergeCells(`A${row}:D${row}`);
    row++;

    // Table Headers
    const headers = ["Severity", "Flag", "Description", "Key Metrics"];
    headers.forEach((header, idx) => {
      const cell = sheet.getCell(row, idx + 1);
      cell.value = header;
      applySectionHeaderStyle(cell);
    });
    row++;

    // Render each flag
    flags.forEach((flag, index) => {
      const startRow = row;

      // Severity cell with color coding
      const severityCell = sheet.getCell(`A${row}`);
      severityCell.value = flag.severity || "Unknown";
      severityCell.font = { ...FONTS.label, bold: true, color: { argb: "FFFFFFFF" } };
      severityCell.alignment = { horizontal: "center", vertical: "middle" };

      // Color code by severity
      let bgColor = "FF9CA3AF"; // Gray for Low/Unknown
      if (flag.severity === "High") bgColor = "FFDC2626"; // Red
      else if (flag.severity === "Medium") bgColor = "FFF59E0B"; // Yellow/Orange

      severityCell.fill = {
        type: "pattern",
        pattern: "solid",
        fgColor: { argb: bgColor },
      };

      // Flag name
      const flagCell = sheet.getCell(`B${row}`);
      flagCell.value = flag.flag || "Unknown Risk";
      flagCell.font = { ...FONTS.label, bold: true };

      // Description
      const descCell = sheet.getCell(`C${row}`);
      descCell.value = flag.description || "";
      descCell.font = FONTS.body;
      descCell.alignment = { wrapText: true, vertical: "top" };

      // Metrics
      const metricsCell = sheet.getCell(`D${row}`);
      if (flag.metrics && Object.keys(flag.metrics).length > 0) {
        const metricsText = Object.entries(flag.metrics)
          .map(([key, value]) => {
            const formattedKey = key.replace(/_/g, " ");
            const formattedValue =
              typeof value === "number"
                ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
                : Array.isArray(value)
                ? value.join(", ")
                : String(value);
            return `${formattedKey}: ${formattedValue}`;
          })
          .join("\n");
        metricsCell.value = metricsText;
      } else {
        metricsCell.value = "N/A";
      }
      metricsCell.font = { ...FONTS.body, size: 9 };
      metricsCell.alignment = { wrapText: true, vertical: "top" };

      // Set row height for readability
      sheet.getRow(row).height = 60;

      // Apply borders
      ["A", "B", "C", "D"].forEach((col) => {
        const cell = sheet.getCell(`${col}${row}`);
        cell.border = {
          top: { style: "thin", color: { argb: "FFE5E7EB" } },
          bottom: { style: "thin", color: { argb: "FFE5E7EB" } },
          left: { style: "thin", color: { argb: "FFE5E7EB" } },
          right: { style: "thin", color: { argb: "FFE5E7EB" } },
        };
      });

      row++;
    });

    row++; // Space between categories
  });

  // Set column widths
  sheet.getColumn(1).width = 12; // Severity
  sheet.getColumn(2).width = 28; // Flag
  sheet.getColumn(3).width = 50; // Description
  sheet.getColumn(4).width = 35; // Metrics

  // Freeze header row
  sheet.views = [{ state: "frozen", ySplit: 1 }];
}
