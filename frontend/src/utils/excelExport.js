// src/utils/excelExport.js
import * as XLSX from "xlsx";
// eslint-disable-next-line no-unused-vars
import { formatCurrency, formatPercentage, safeText } from "./formatters";

/**
 * Export CIM data to a beautifully formatted Excel file
 * Designed for PE/VC analysts
 */
export function exportToExcel(data, metadata) {
  const workbook = XLSX.utils.book_new();

  // 1. Executive Summary Sheet
  addExecutiveSummary(workbook, data, metadata);

  // 2. Company Overview Sheet
  addCompanyOverview(workbook, data);

  // 3. Financial Performance Sheet (with charts data)
  addFinancialPerformance(workbook, data);

  // 4. Balance Sheet & Ratios Sheet
  addBalanceSheetAndRatios(workbook, data);

  // 5. Customer & Market Analysis Sheet
  addCustomerMarketAnalysis(workbook, data);

  // 6. Investment Memo Sheet
  addInvestmentMemo(workbook, data);

  // 7. Risk Analysis Sheet
  addRiskAnalysis(workbook, data);

  // 8. Management Team Sheet
  addManagementTeam(workbook, data);

  // Generate filename with company name and date
  const companyName = data.company_info?.company_name || "Company";
  const dateStr = new Date().toISOString().split("T")[0];
  const filename = `${sanitizeFilename(
    companyName
  )}_CIM_Analysis_${dateStr}.xlsx`;

  // Write the file
  XLSX.writeFile(workbook, filename);
}

// Helper function to sanitize filename
function sanitizeFilename(name) {
  return name.replace(/[^a-z0-9]/gi, "_").substring(0, 50);
}

// 1. EXECUTIVE SUMMARY SHEET
function addExecutiveSummary(workbook, data, metadata) {
  const ws_data = [];

  // Header
  ws_data.push(["CONFIDENTIAL INFORMATION MEMORANDUM"]);
  ws_data.push(["Executive Summary"]);
  ws_data.push([]);

  // Company Info
  ws_data.push(["COMPANY INFORMATION"]);
  ws_data.push(["Company Name:", data.company_info?.company_name || "N/A"]);
  ws_data.push(["Industry:", data.company_info?.industry || "N/A"]);
  if (data.company_info?.secondary_industry) {
    ws_data.push(["Secondary Industry:", data.company_info.secondary_industry]);
  }
  ws_data.push(["Headquarters:", data.company_info?.headquarters || "N/A"]);
  ws_data.push(["Employees:", data.company_info?.employees || "N/A"]);
  ws_data.push(["Founded:", data.company_info?.founded_year || "N/A"]);
  ws_data.push([]);

  // Transaction Overview
  if (
    data.transaction_details &&
    Object.values(data.transaction_details).some((v) => v != null)
  ) {
    ws_data.push(["TRANSACTION OVERVIEW"]);
    if (data.transaction_details.asking_price) {
      ws_data.push(["Asking Price:", data.transaction_details.asking_price]);
    }
    if (data.transaction_details.deal_type) {
      ws_data.push(["Deal Type:", data.transaction_details.deal_type]);
    }
    if (data.transaction_details.implied_valuation_hint) {
      ws_data.push([
        "Valuation Multiples:",
        data.transaction_details.implied_valuation_hint,
      ]);
    }
    ws_data.push([]);
  }

  // Key Metrics
  ws_data.push(["KEY FINANCIAL METRICS"]);
  const financials = data.financials || {};

  // Latest Revenue
  if (
    financials.revenue_by_year &&
    Object.keys(financials.revenue_by_year).length > 0
  ) {
    const years = Object.keys(financials.revenue_by_year).sort().reverse();
    ws_data.push([
      "Latest Revenue:",
      financials.revenue_by_year[years[0]],
      years[0],
    ]);
  }

  // Latest EBITDA
  if (
    financials.adjusted_ebitda_by_year &&
    Object.keys(financials.adjusted_ebitda_by_year).length > 0
  ) {
    const years = Object.keys(financials.adjusted_ebitda_by_year)
      .sort()
      .reverse();
    ws_data.push([
      "Latest Adj. EBITDA:",
      financials.adjusted_ebitda_by_year[years[0]],
      years[0],
    ]);
  }

  // Key Ratios
  const ratios = data.financial_ratios || {};
  if (ratios.ebitda_margin != null) {
    ws_data.push(["EBITDA Margin:", ratios.ebitda_margin]);
  }
  if (ratios.net_debt_to_ebitda != null) {
    ws_data.push(["Net Debt / EBITDA:", ratios.net_debt_to_ebitda]);
  }
  ws_data.push([]);

  // Growth Metrics
  if (
    data.growth_analysis &&
    Object.values(data.growth_analysis).some((v) => v != null)
  ) {
    ws_data.push(["GROWTH METRICS"]);
    if (data.growth_analysis.historical_cagr != null) {
      ws_data.push(["Historical CAGR:", data.growth_analysis.historical_cagr]);
    }
    if (data.growth_analysis.projected_cagr != null) {
      ws_data.push(["Projected CAGR:", data.growth_analysis.projected_cagr]);
    }
    ws_data.push([]);
  }

  // Metadata
  ws_data.push(["DOCUMENT INFORMATION"]);
  ws_data.push(["Pages Processed:", metadata?.pages || "N/A"]);
  ws_data.push(["Extraction Date:", new Date().toLocaleDateString()]);
  ws_data.push(["Request ID:", metadata?.request_id || "N/A"]);

  const ws = XLSX.utils.aoa_to_sheet(ws_data);

  // Styling: Set column widths
  ws["!cols"] = [
    { wch: 25 }, // Column A
    { wch: 20 }, // Column B
    { wch: 15 }, // Column C
  ];

  XLSX.utils.book_append_sheet(workbook, ws, "Executive Summary");
}

// 2. COMPANY OVERVIEW SHEET
function addCompanyOverview(workbook, data) {
  const ws_data = [];

  ws_data.push(["COMPANY OVERVIEW"]);
  ws_data.push([]);

  const company = data.company_info || {};

  ws_data.push(["Field", "Value"]);
  ws_data.push(["Company Name", company.company_name || "N/A"]);
  ws_data.push(["Company ID", company.company_id || "N/A"]);
  ws_data.push(["Industry", company.industry || "N/A"]);
  ws_data.push(["Secondary Industry", company.secondary_industry || "N/A"]);
  ws_data.push(["Business Structure", company.business_structure || "N/A"]);
  ws_data.push(["Founded Year", company.founded_year || "N/A"]);
  ws_data.push(["Employees", company.employees || "N/A"]);
  ws_data.push(["Headquarters", company.headquarters || "N/A"]);
  ws_data.push(["Website", company.website || "N/A"]);
  ws_data.push([]);

  // Investment Thesis
  if (data.investment_thesis) {
    ws_data.push(["INVESTMENT THESIS"]);
    ws_data.push([]);
    const thesisLines = data.investment_thesis.split("\n");
    thesisLines.forEach((line) => {
      ws_data.push([line]);
    });
  }

  const ws = XLSX.utils.aoa_to_sheet(ws_data);
  ws["!cols"] = [{ wch: 30 }, { wch: 60 }];

  XLSX.utils.book_append_sheet(workbook, ws, "Company Overview");
}

// 3. FINANCIAL PERFORMANCE SHEET
function addFinancialPerformance(workbook, data) {
  const financials = data.financials || {};
  const ws_data = [];

  ws_data.push(["FINANCIAL PERFORMANCE"]);
  ws_data.push([]);
  ws_data.push(["Currency:", financials.currency || "USD"]);
  ws_data.push(["Fiscal Year End:", financials.fiscal_year_end || "N/A"]);
  ws_data.push([]);

  // Get all years across all metrics
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
    const headers = [
      "Metric",
      ...sortedYears.map(
        (y) =>
          y.replace("projected_", "") +
          (y.startsWith("projected_") ? " (P)" : "")
      ),
    ];
    ws_data.push(headers);

    // Revenue
    if (financials.revenue_by_year) {
      const row = ["Revenue"];
      sortedYears.forEach((year) => {
        row.push(financials.revenue_by_year[year] || "");
      });
      ws_data.push(row);
    }

    // EBITDA
    if (financials.ebitda_by_year) {
      const row = ["EBITDA"];
      sortedYears.forEach((year) => {
        row.push(financials.ebitda_by_year[year] || "");
      });
      ws_data.push(row);
    }

    // Adjusted EBITDA
    if (financials.adjusted_ebitda_by_year) {
      const row = ["Adjusted EBITDA"];
      sortedYears.forEach((year) => {
        row.push(financials.adjusted_ebitda_by_year[year] || "");
      });
      ws_data.push(row);
    }

    // Net Income
    if (financials.net_income_by_year) {
      const row = ["Net Income"];
      sortedYears.forEach((year) => {
        row.push(financials.net_income_by_year[year] || "");
      });
      ws_data.push(row);
    }

    // Gross Margin
    if (financials.gross_margin_by_year) {
      const row = ["Gross Margin (%)"];
      sortedYears.forEach((year) => {
        const val = financials.gross_margin_by_year[year];
        row.push(val != null ? val * 100 : "");
      });
      ws_data.push(row);
    }
  }

  ws_data.push([]);

  // Other Metrics
  if (
    financials.other_metrics &&
    Object.keys(financials.other_metrics).length > 0
  ) {
    ws_data.push(["OTHER FINANCIAL METRICS"]);
    ws_data.push(["Metric", "Value"]);
    Object.entries(financials.other_metrics).forEach(([key, value]) => {
      const label = key
        .replace(/_/g, " ")
        .replace(/\b\w/g, (l) => l.toUpperCase());
      ws_data.push([label, value]);
    });
  }

  const ws = XLSX.utils.aoa_to_sheet(ws_data);

  // Set column widths
  const colWidths = [{ wch: 25 }];
  sortedYears.forEach(() => colWidths.push({ wch: 15 }));
  ws["!cols"] = colWidths;

  XLSX.utils.book_append_sheet(workbook, ws, "Financial Performance");
}

// 4. BALANCE SHEET & RATIOS SHEET
function addBalanceSheetAndRatios(workbook, data) {
  const balance = data.balance_sheet || {};
  const ratios = data.financial_ratios || {};
  const ws_data = [];

  // Balance Sheet Section
  ws_data.push(["BALANCE SHEET"]);
  if (balance.most_recent_year) {
    ws_data.push(["Most Recent Year:", balance.most_recent_year]);
  }
  ws_data.push([]);

  ws_data.push(["Item", "Amount"]);
  ws_data.push(["ASSETS", ""]);
  if (balance.total_assets != null)
    ws_data.push(["Total Assets", balance.total_assets]);
  if (balance.current_assets != null)
    ws_data.push(["  Current Assets", balance.current_assets]);
  if (balance.fixed_assets != null)
    ws_data.push(["  Fixed Assets", balance.fixed_assets]);

  ws_data.push([]);
  ws_data.push(["LIABILITIES & EQUITY", ""]);
  if (balance.total_liabilities != null)
    ws_data.push(["Total Liabilities", balance.total_liabilities]);
  if (balance.current_liabilities != null)
    ws_data.push(["  Current Liabilities", balance.current_liabilities]);
  if (balance.long_term_debt != null)
    ws_data.push(["  Long-Term Debt", balance.long_term_debt]);
  if (balance.stockholders_equity != null)
    ws_data.push(["Stockholders Equity", balance.stockholders_equity]);
  if (balance.working_capital != null)
    ws_data.push(["Working Capital", balance.working_capital]);

  ws_data.push([]);
  ws_data.push([]);

  // Financial Ratios Section
  ws_data.push(["FINANCIAL RATIOS"]);
  ws_data.push([]);

  // Key PE Metrics
  ws_data.push(["KEY PE METRICS", "Value"]);
  if (ratios.ebitda_margin != null)
    ws_data.push(["EBITDA Margin", ratios.ebitda_margin]);
  if (ratios.net_debt_to_ebitda != null)
    ws_data.push(["Net Debt / EBITDA", ratios.net_debt_to_ebitda]);
  if (ratios.capex_pct_revenue != null)
    ws_data.push(["CapEx % of Revenue", ratios.capex_pct_revenue]);
  if (ratios.return_on_equity != null)
    ws_data.push(["Return on Equity", ratios.return_on_equity]);

  ws_data.push([]);

  // Liquidity Ratios
  ws_data.push(["LIQUIDITY RATIOS", "Value"]);
  if (ratios.current_ratio != null)
    ws_data.push(["Current Ratio", ratios.current_ratio]);
  if (ratios.quick_ratio != null)
    ws_data.push(["Quick Ratio", ratios.quick_ratio]);

  ws_data.push([]);

  // Leverage & Profitability
  ws_data.push(["LEVERAGE & PROFITABILITY", "Value"]);
  if (ratios.debt_to_equity != null)
    ws_data.push(["Debt to Equity", ratios.debt_to_equity]);
  if (ratios.return_on_assets != null)
    ws_data.push(["Return on Assets", ratios.return_on_assets]);

  ws_data.push([]);

  // Efficiency Ratios
  ws_data.push(["EFFICIENCY RATIOS", "Value"]);
  if (ratios.inventory_turnover != null)
    ws_data.push(["Inventory Turnover", ratios.inventory_turnover]);
  if (ratios.accounts_receivable_turnover != null)
    ws_data.push(["A/R Turnover", ratios.accounts_receivable_turnover]);

  const ws = XLSX.utils.aoa_to_sheet(ws_data);
  ws["!cols"] = [{ wch: 30 }, { wch: 20 }];

  XLSX.utils.book_append_sheet(workbook, ws, "Balance Sheet & Ratios");
}

// 5. CUSTOMER & MARKET ANALYSIS SHEET
function addCustomerMarketAnalysis(workbook, data) {
  const customers = data.customers || {};
  const market = data.market || {};
  const ws_data = [];

  // Customer Metrics
  ws_data.push(["CUSTOMER METRICS"]);
  ws_data.push([]);
  ws_data.push(["Metric", "Value"]);

  if (customers.total_count != null)
    ws_data.push(["Total Customers", customers.total_count]);
  if (customers.top_customer_concentration)
    ws_data.push([
      "Top Customer Concentration",
      customers.top_customer_concentration,
    ]);
  if (customers.top_customer_concentration_pct != null)
    ws_data.push(["Top Customer %", customers.top_customer_concentration_pct]);
  if (customers.customer_retention_rate)
    ws_data.push(["Retention Rate", customers.customer_retention_rate]);
  if (customers.recurring_revenue_pct != null)
    ws_data.push(["Recurring Revenue %", customers.recurring_revenue_pct]);

  ws_data.push([]);

  // Revenue Mix
  if (
    customers.revenue_mix_by_segment &&
    Object.keys(customers.revenue_mix_by_segment).length > 0
  ) {
    ws_data.push(["REVENUE MIX BY SEGMENT"]);
    ws_data.push(["Segment", "Percentage"]);
    Object.entries(customers.revenue_mix_by_segment).forEach(
      ([segment, pct]) => {
        ws_data.push([segment, pct]);
      }
    );
    ws_data.push([]);
  }

  // Notable Customers
  if (
    Array.isArray(customers.notable_customers) &&
    customers.notable_customers.length > 0
  ) {
    ws_data.push(["NOTABLE CUSTOMERS"]);
    customers.notable_customers.forEach((customer) => {
      ws_data.push([customer]);
    });
    ws_data.push([]);
  }

  ws_data.push([]);

  // Market Analysis
  ws_data.push(["MARKET ANALYSIS"]);
  ws_data.push([]);
  ws_data.push(["Metric", "Value"]);

  if (market.market_size) ws_data.push(["Market Size", market.market_size]);
  if (market.market_size_estimate != null)
    ws_data.push(["Market Size (Estimate)", market.market_size_estimate]);
  if (market.market_growth_rate)
    ws_data.push(["Market Growth Rate", market.market_growth_rate]);
  if (market.competitive_position)
    ws_data.push(["Competitive Position", market.competitive_position]);
  if (market.market_share) ws_data.push(["Market Share", market.market_share]);

  const ws = XLSX.utils.aoa_to_sheet(ws_data);
  ws["!cols"] = [{ wch: 30 }, { wch: 40 }];

  XLSX.utils.book_append_sheet(workbook, ws, "Customer & Market");
}

// 6. INVESTMENT MEMO SHEET
function addInvestmentMemo(workbook, data) {
  const ws_data = [];
  const tx = data.transaction_details || {};
  const growth = data.growth_analysis || {};
  const derived = data.derived_metrics || {};

  ws_data.push(["INVESTMENT MEMORANDUM"]);
  ws_data.push([]);

  // Transaction Details
  ws_data.push(["TRANSACTION DETAILS"]);
  ws_data.push(["Field", "Value"]);
  if (tx.deal_type) ws_data.push(["Deal Type", tx.deal_type]);
  if (tx.asking_price != null) ws_data.push(["Asking Price", tx.asking_price]);
  if (tx.implied_valuation_hint)
    ws_data.push(["Valuation Multiples", tx.implied_valuation_hint]);
  if (tx.assets_for_sale) ws_data.push(["Assets for Sale", tx.assets_for_sale]);
  if (tx.auction_deadline)
    ws_data.push(["Auction Deadline", tx.auction_deadline]);
  ws_data.push([]);

  if (tx.seller_motivation) {
    ws_data.push(["Seller Motivation:"]);
    ws_data.push([tx.seller_motivation]);
    ws_data.push([]);
  }

  if (tx.post_sale_involvement) {
    ws_data.push(["Post-Sale Involvement:"]);
    ws_data.push([tx.post_sale_involvement]);
    ws_data.push([]);
  }

  // Growth Analysis
  if (Object.values(growth).some((v) => v != null)) {
    ws_data.push(["GROWTH ANALYSIS"]);
    ws_data.push(["Metric", "Value"]);
    if (growth.historical_cagr != null)
      ws_data.push(["Historical CAGR", growth.historical_cagr]);
    if (growth.projected_cagr != null)
      ws_data.push(["Projected CAGR", growth.projected_cagr]);
    if (growth.organic_pct != null)
      ws_data.push(["Organic Growth %", growth.organic_pct]);
    if (growth.m_and_a_pct != null)
      ws_data.push(["M&A Growth %", growth.m_and_a_pct]);
    ws_data.push([]);
  }

  // Derived Metrics
  if (Object.keys(derived).length > 0) {
    ws_data.push(["DERIVED METRICS"]);
    ws_data.push(["Metric", "Value"]);
    Object.entries(derived).forEach(([key, value]) => {
      const label = key
        .replace(/_/g, " ")
        .replace(/\b\w/g, (l) => l.toUpperCase());
      ws_data.push([label, value]);
    });
    ws_data.push([]);
  }

  // Investment Thesis
  if (data.investment_thesis) {
    ws_data.push(["INVESTMENT THESIS"]);
    ws_data.push([]);
    const thesisLines = data.investment_thesis.split("\n");
    thesisLines.forEach((line) => {
      ws_data.push([line]);
    });
  }

  const ws = XLSX.utils.aoa_to_sheet(ws_data);
  ws["!cols"] = [{ wch: 30 }, { wch: 60 }];

  XLSX.utils.book_append_sheet(workbook, ws, "Investment Memo");
}

// 7. RISK ANALYSIS SHEET
function addRiskAnalysis(workbook, data) {
  const ws_data = [];

  ws_data.push(["RISK ANALYSIS"]);
  ws_data.push([]);

  if (Array.isArray(data.key_risks) && data.key_risks.length > 0) {
    ws_data.push([
      "#",
      "Severity",
      "Risk",
      "Description",
      "Mitigation",
      "Source",
    ]);

    data.key_risks.forEach((risk, index) => {
      if (typeof risk === "object") {
        ws_data.push([
          index + 1,
          risk.severity || "N/A",
          risk.risk || "N/A",
          risk.description || "",
          risk.mitigation || "",
          risk.inferred ? "Inferred" : "Explicit",
        ]);
      } else {
        ws_data.push([index + 1, "", risk, "", "", ""]);
      }
    });
  } else {
    ws_data.push(["No risks identified"]);
  }

  const ws = XLSX.utils.aoa_to_sheet(ws_data);
  ws["!cols"] = [
    { wch: 5 }, // #
    { wch: 12 }, // Severity
    { wch: 25 }, // Risk
    { wch: 50 }, // Description
    { wch: 50 }, // Mitigation
    { wch: 12 }, // Source
  ];

  XLSX.utils.book_append_sheet(workbook, ws, "Risk Analysis");
}

// 8. MANAGEMENT TEAM SHEET
function addManagementTeam(workbook, data) {
  const ws_data = [];

  ws_data.push(["MANAGEMENT TEAM"]);
  ws_data.push([]);

  if (Array.isArray(data.management_team) && data.management_team.length > 0) {
    ws_data.push(["Name", "Title", "Background", "LinkedIn"]);

    data.management_team.forEach((member) => {
      ws_data.push([
        member.name || "N/A",
        member.title || "N/A",
        member.background || "",
        member.linkedin || "",
      ]);
    });
  } else {
    ws_data.push(["No management team information available"]);
  }

  const ws = XLSX.utils.aoa_to_sheet(ws_data);
  ws["!cols"] = [
    { wch: 25 }, // Name
    { wch: 30 }, // Title
    { wch: 60 }, // Background
    { wch: 40 }, // LinkedIn
  ];

  XLSX.utils.book_append_sheet(workbook, ws, "Management Team");
}
