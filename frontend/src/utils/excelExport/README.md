# Excel Export Module

This module handles the generation of professional Excel reports for CIM (Confidential Information Memorandum) documents, designed specifically for PE/VC analysts.

## Structure

```
excelExport/
├── index.js                  # Main entry point, orchestrates all sheet generation
├── styles.js                 # Centralized styling utilities (colors, fonts, formatters)
├── executiveSummary.js       # Executive Summary sheet
├── companyOverview.js        # Company Overview & Profile sheet
├── financialPerformance.js   # Financial Performance sheet with charts
└── otherSheets.js            # All other sheets (consolidated for simplicity)
    ├── Balance Sheet & Ratios
    ├── Valuation Multiples
    ├── Capital Structure
    ├── Operating Metrics
    ├── Customer & Market Analysis
    ├── Strategic Rationale
    ├── Investment Memo
    ├── Risk Analysis
    └── Management Team
```

## Features

### Professional Styling
- **Color scheme**: Professional blue/gray palette
- **Typography**: Calibri font with proper hierarchy
- **Borders**: Thick colored section separators
- **Alternating row colors**: Better readability
- **No gridlines**: Clean, polished appearance

### Advanced Formatting
- **Currency**: `$#,##0.00` format
- **Percentages**: `0.00%` format
- **Multiples**: `0.0"x"` format (e.g., "5.2x")
- **Hyperlinks**: Clickable LinkedIn URLs
- **Text wrapping**: Automatic for long content

### Dynamic Features
- **Formulas**: EBITDA Margin automatically calculated from data
- **Charts**: Revenue & EBITDA growth trend line chart
- **Color-coded risks**: High (red), Medium (yellow), Low (green)

## Usage

```javascript
import { exportToExcel } from './utils/excelExport';

// Call from your component
await exportToExcel(data, metadata);
```

## Technology

- **Library**: [ExcelJS](https://github.com/exceljs/exceljs) (MIT License)
- **File format**: `.xlsx` (Excel 2007+)
- **Browser compatibility**: Modern browsers with Blob API support

## Maintenance

### Adding a new sheet
1. Create a new file (e.g., `newSheet.js`)
2. Import styling utilities from `styles.js`
3. Export a function that accepts `(workbook, data)`
4. Import and call it in `index.js`

### Modifying styles
All styling constants and utilities are centralized in `styles.js`

### Adding charts
Charts are added using ExcelJS's chart API. See `financialPerformance.js` for examples.

## License

Uses ExcelJS (MIT License) - safe for redistribution and commercial use.
