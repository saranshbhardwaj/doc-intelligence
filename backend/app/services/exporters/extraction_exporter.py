"""Extraction (CIM) exporter - Word and Excel.

Handles extraction results with proper ExtractedData model support.
"""

from typing import Dict, Any, Tuple
from datetime import datetime
from io import BytesIO
import pandas as pd

from .base_exporter import BaseExporter
from app.models import ExtractedData


class ExtractionExporter(BaseExporter):
    """
    Exporter for extraction results (CIM analysis).

    Input: ExtractedData model (from models.py)
    Output: Professional Word/Excel documents

    Type Safety:
    - Input: Dict[str, Any] that conforms to ExtractedData schema
    - Validation: Pydantic model ensures type safety
    - Output: bytes (Word/Excel file content)
    """

    def export_to_word(
        self,
        data: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> Tuple[bytes, str, str]:
        """
        Export extraction to Word document.

        Args:
            data: ExtractedData dict (validated by Pydantic)
            metadata: Extraction metadata (filename, pages, etc.)

        Returns:
            Tuple of (bytes, filename, content_type)

        Raises:
            ValueError: If data doesn't conform to ExtractedData schema
        """
        # Validate input with Pydantic model
        try:
            extracted_data = ExtractedData(**data)
        except Exception as e:
            raise ValueError(f"Invalid extraction data: {e}")

        self.create_document()

        # Cover page
        company_name = (
            extracted_data.company_info.company_name
            if extracted_data.company_info
            else metadata.get('filename', 'Company')
        )

        self.add_title("Confidential Information Memorandum")
        self.add_title(company_name)

        # Metadata
        self.add_paragraph(
            f"Analysis Date: {datetime.now().strftime('%B %d, %Y')}",
            bold=True
        )

        if metadata.get('filename'):
            self.add_paragraph(f"Source: {metadata['filename']}")

        self.add_divider()

        # Executive Summary (if present in raw_sections or as field)
        if extracted_data.raw_sections and 'Executive Summary' in extracted_data.raw_sections:
            self.add_heading("Executive Summary", level=1)
            exec_summary = extracted_data.raw_sections['Executive Summary']
            summary_text = exec_summary.get('text') if isinstance(exec_summary, dict) else str(exec_summary)
            self.add_paragraph(summary_text)

        # Company Overview
        if extracted_data.company_info:
            self.add_heading("Company Overview", level=1)
            self._add_company_info(extracted_data.company_info)

        # Financial Highlights
        if extracted_data.financials:
            self.add_heading("Financial Highlights", level=1)
            self._add_financials(extracted_data.financials)

        # Balance Sheet
        if extracted_data.balance_sheet and extracted_data.balance_sheet.total_assets:
            self.add_heading("Balance Sheet", level=1)
            self._add_balance_sheet(extracted_data.balance_sheet)

        # Financial Ratios
        if extracted_data.financial_ratios:
            self.add_heading("Financial Ratios", level=1)
            self._add_financial_ratios(extracted_data.financial_ratios)

        # Valuation Multiples
        if extracted_data.valuation_multiples:
            self.add_heading("Valuation Multiples", level=1)
            self._add_valuation_multiples(extracted_data.valuation_multiples)

        # Capital Structure
        if extracted_data.capital_structure:
            self.add_heading("Capital Structure", level=1)
            self._add_capital_structure(extracted_data.capital_structure)

        # Operating Metrics
        if extracted_data.operating_metrics:
            self.add_heading("Operating Metrics", level=1)
            self._add_operating_metrics(extracted_data.operating_metrics)

        # Customer & Market Analysis
        if extracted_data.customers or extracted_data.market:
            self.add_heading("Customer & Market Analysis", level=1)
            if extracted_data.customers:
                self._add_customer_info(extracted_data.customers)
            if extracted_data.market:
                self._add_market_info(extracted_data.market)

        # Investment Thesis
        if extracted_data.investment_thesis:
            self.add_heading("Investment Thesis", level=1)
            self.add_paragraph(extracted_data.investment_thesis)

        # Key Risks & Red Flags
        if extracted_data.key_risks or extracted_data.red_flags:
            self.add_heading("Risk Analysis", level=1)
            if extracted_data.key_risks:
                self._add_risks(extracted_data.key_risks)
            if extracted_data.red_flags:
                self._add_red_flags(extracted_data.red_flags)

        # Strategic Rationale
        if extracted_data.strategic_rationale:
            self.add_heading("Strategic Rationale", level=1)
            self._add_strategic_rationale(extracted_data.strategic_rationale)

        # Management Team
        if extracted_data.management_team:
            self.add_heading("Management Team", level=1)
            self._add_management_team(extracted_data.management_team)

        # Transaction Details
        if extracted_data.transaction_details:
            self.add_heading("Transaction Details", level=1)
            self._add_transaction_details(extracted_data.transaction_details)

        # Footer
        self.add_divider()
        self.add_footer_text("This is a confidential document prepared for investment evaluation purposes.")
        self.add_footer_text("Generated using AI-powered document intelligence from Sand Cloud.")

        if metadata.get('processing_time_ms'):
            self.add_footer_text(f"Processing Time: {metadata['processing_time_ms']}ms")

        # Generate filename and return
        filename = self.sanitize_filename(f"{company_name}_CIM_Analysis.docx")
        content = self.save_to_bytes()

        return (
            content,
            filename,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    def _add_company_info(self, company_info):
        """Add company information section."""
        if company_info.company_name:
            self.add_paragraph(f"Company: {company_info.company_name}", bold=True)
        if company_info.industry:
            self.add_paragraph(f"Industry: {company_info.industry}")
        if company_info.founded_year:
            self.add_paragraph(f"Founded: {company_info.founded_year}")
        if company_info.headquarters:
            self.add_paragraph(f"Headquarters: {company_info.headquarters}")
        if company_info.employees:
            self.add_paragraph(f"Employees: {company_info.employees:,}")
        if company_info.website:
            self.add_paragraph(f"Website: {company_info.website}")

    def _add_financials(self, financials):
        """Add financial highlights."""
        if financials.currency:
            self.add_paragraph(f"Currency: {financials.currency}", bold=True)

        if financials.revenue_by_year:
            self.add_heading("Revenue by Year", level=2)
            for year, value in sorted(financials.revenue_by_year.items()):
                self.add_paragraph(f"{year}: {financials.currency} {value:,.0f}")

        if financials.ebitda_by_year:
            self.add_heading("EBITDA by Year", level=2)
            for year, value in sorted(financials.ebitda_by_year.items()):
                self.add_paragraph(f"{year}: {financials.currency} {value:,.0f}")

    def _add_balance_sheet(self, balance_sheet):
        """Add balance sheet section."""
        if balance_sheet.most_recent_year:
            self.add_paragraph(f"Most Recent Year: {balance_sheet.most_recent_year}", bold=True)
        if balance_sheet.total_assets:
            self.add_paragraph(f"Total Assets: ${balance_sheet.total_assets:,.0f}")
        if balance_sheet.total_liabilities:
            self.add_paragraph(f"Total Liabilities: ${balance_sheet.total_liabilities:,.0f}")
        if balance_sheet.stockholders_equity:
            self.add_paragraph(f"Stockholders' Equity: ${balance_sheet.stockholders_equity:,.0f}")

    def _add_financial_ratios(self, ratios):
        """Add financial ratios."""
        if ratios.current_ratio:
            self.add_paragraph(f"Current Ratio: {ratios.current_ratio:.2f}")
        if ratios.debt_to_equity:
            self.add_paragraph(f"Debt-to-Equity: {ratios.debt_to_equity:.2f}")
        if ratios.return_on_assets:
            self.add_paragraph(f"Return on Assets: {ratios.return_on_assets:.1%}")
        if ratios.ebitda_margin:
            self.add_paragraph(f"EBITDA Margin: {ratios.ebitda_margin:.1%}")

    def _add_valuation_multiples(self, multiples):
        """Add valuation multiples."""
        if multiples.asking_ev_ebitda:
            self.add_paragraph(f"Asking EV/EBITDA: {multiples.asking_ev_ebitda:.1f}x")
        if multiples.asking_ev_revenue:
            self.add_paragraph(f"Asking EV/Revenue: {multiples.asking_ev_revenue:.1f}x")
        if multiples.comparable_multiples_range:
            self.add_paragraph(f"Comparable Multiples: {multiples.comparable_multiples_range}")

    def _add_capital_structure(self, capital):
        """Add capital structure."""
        if capital.existing_debt:
            self.add_paragraph(f"Existing Debt: ${capital.existing_debt:,.0f}")
        if capital.debt_to_ebitda:
            self.add_paragraph(f"Debt/EBITDA: {capital.debt_to_ebitda:.1f}x")
        if capital.proposed_leverage:
            self.add_paragraph(f"Proposed Leverage: {capital.proposed_leverage:.1f}x")

    def _add_operating_metrics(self, metrics):
        """Add operating metrics."""
        if metrics.pricing_power:
            self.add_paragraph(f"Pricing Power: {metrics.pricing_power}")
        if metrics.contract_structure:
            self.add_paragraph(f"Contract Structure: {metrics.contract_structure}")

    def _add_customer_info(self, customers):
        """Add customer information."""
        self.add_heading("Customer Analysis", level=2)
        if customers.total_count:
            self.add_paragraph(f"Total Customers: {customers.total_count:,}")
        if customers.top_customer_concentration:
            self.add_paragraph(f"Top Customer Concentration: {customers.top_customer_concentration}")
        if customers.customer_retention_rate:
            self.add_paragraph(f"Retention Rate: {customers.customer_retention_rate}")

    def _add_market_info(self, market):
        """Add market information."""
        self.add_heading("Market Analysis", level=2)
        if market.market_size:
            self.add_paragraph(f"Market Size: {market.market_size}")
        if market.market_growth_rate:
            self.add_paragraph(f"Growth Rate: {market.market_growth_rate}")
        if market.competitive_position:
            self.add_paragraph(f"Competitive Position: {market.competitive_position}")

    def _add_risks(self, risks):
        """Add key risks."""
        for risk in risks:
            risk_text = risk.risk if hasattr(risk, 'risk') else str(risk)
            para = self.add_paragraph(f"⚠️ {risk_text}")
            if hasattr(risk, 'severity') and risk.severity:
                para.add_run(f" ({risk.severity})").bold = True

    def _add_red_flags(self, red_flags):
        """Add automated red flags."""
        self.add_heading("Red Flags (Automated Detection)", level=2)
        for flag in red_flags:
            flag_text = flag.get('flag') or flag.get('message') or str(flag)
            self.add_paragraph(f"🚩 {flag_text}")

    def _add_strategic_rationale(self, rationale):
        """Add strategic rationale."""
        if rationale.deal_thesis:
            self.add_heading("Deal Thesis", level=2)
            self.add_paragraph(rationale.deal_thesis)
        if rationale.value_creation_plan:
            self.add_heading("Value Creation Plan", level=2)
            self.add_paragraph(rationale.value_creation_plan)

    def _add_management_team(self, team):
        """Add management team."""
        for member in team:
            name = member.name if hasattr(member, 'name') else str(member)
            self.add_paragraph(name, bold=True)
            if hasattr(member, 'title') and member.title:
                self.add_paragraph(f"Title: {member.title}")
            if hasattr(member, 'background') and member.background:
                self.add_paragraph(member.background)

    def _add_transaction_details(self, transaction):
        """Add transaction details."""
        if transaction.deal_type:
            self.add_paragraph(f"Deal Type: {transaction.deal_type}")
        if transaction.asking_price:
            self.add_paragraph(f"Asking Price: ${transaction.asking_price:,.0f}")
        if transaction.seller_motivation:
            self.add_paragraph(f"Seller Motivation: {transaction.seller_motivation}")

    def export_to_excel(
        self,
        data: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> Tuple[bytes, str, str]:
        """
        Export extraction to Excel (reuses existing to_xlsx_bytes logic).

        Args:
            data: ExtractedData dict
            metadata: Extraction metadata

        Returns:
            Tuple of (bytes, filename, content_type)
        """
        # Reuse the existing Excel export from exporter.py
        from app.services.exporter import to_xlsx_bytes

        content, filename = to_xlsx_bytes(data)

        return (
            content,
            filename,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
