// excelExport/styles.js
// Centralized styling utilities for Excel export

export const COLORS = {
  primary: "0066CC",
  secondary: "4A90E2",
  success: "28A745",
  warning: "FFC107",
  danger: "DC3545",
  headerBg: "2C3E50",
  sectionBg: "ECF0F1",
  lightGray: "F8F9FA",
  darkText: "2C3E50",
};

export const FONTS = {
  header: { name: "Calibri", size: 16, bold: true, color: { argb: "FFFFFFFF" } },
  sectionHeader: { name: "Calibri", size: 14, bold: true, color: { argb: `FF${COLORS.darkText}` } },
  label: { name: "Calibri", size: 11, bold: true },
  normal: { name: "Calibri", size: 11 },
};

export function applyHeaderStyle(cell, bgColor = COLORS.headerBg) {
  cell.font = FONTS.header;
  cell.fill = {
    type: "pattern",
    pattern: "solid",
    fgColor: { argb: `FF${bgColor}` },
  };
  cell.alignment = { vertical: "middle", horizontal: "left" };
}

export function applySectionHeaderStyle(cell) {
  cell.font = FONTS.sectionHeader;
  cell.fill = {
    type: "pattern",
    pattern: "solid",
    fgColor: { argb: `FF${COLORS.sectionBg}` },
  };
  cell.alignment = { vertical: "middle", horizontal: "left" };
  cell.border = {
    bottom: { style: "thick", color: { argb: `FF${COLORS.primary}` } },
  };
}

export function applyLabelStyle(cell) {
  cell.font = FONTS.label;
  cell.alignment = { vertical: "middle", horizontal: "left" };
}

export function applyValueStyle(cell, isCurrency = false, isPercentage = false) {
  cell.font = FONTS.normal;
  cell.alignment = { vertical: "middle", horizontal: "right" };

  if (isCurrency) {
    cell.numFmt = "$#,##0.00";
  } else if (isPercentage) {
    cell.numFmt = "0.00%";
  }
}

export function applyAlternateRowColor(cell, index) {
  if (index % 2 === 0) {
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: `FF${COLORS.lightGray}` },
    };
  }
}
