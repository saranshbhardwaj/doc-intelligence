"""Workflow exporter - Word and Excel.

Handles workflow results with workflow-specific formatting.
Investment Memo gets special treatment matching the UI.
"""

from typing import Dict, Any, Tuple
from datetime import datetime
from io import BytesIO

from .base_exporter import BaseExporter


class WorkflowExporter(BaseExporter):
    """
    Exporter for workflow results.

    Workflow-Specific Formatting:
    - "Investment Memo" → Special formatting matching InvestmentMemoView
    - Other workflows → Generic markdown processing

    Input: Workflow artifact (Dict[str, Any])
    Output: Professional Word/Excel documents

    Type Safety:
    - Input: Dict[str, Any] (artifact.parsed or artifact.artifact)
    - Output: bytes (Word/Excel file content)
    """

    def export_to_word(
        self,
        artifact: Dict[str, Any],
        run_metadata: Dict[str, Any]
    ) -> Tuple[bytes, str, str]:
        """
        Export workflow to Word document.

        Routing:
        - workflow_name == "Investment Memo" → special formatting
        - Other → generic markdown processing

        Args:
            artifact: Workflow artifact data
            run_metadata: Run metadata (workflow_name, created_at, etc.)

        Returns:
            Tuple of (bytes, filename, content_type)
        """
        workflow_name = run_metadata.get('workflow_name', 'Workflow')

        # Route to workflow-specific exporter
        if workflow_name == 'Investment Memo':
            return self._export_investment_memo(artifact, run_metadata)
        else:
            return self._export_generic_workflow(artifact, run_metadata)

    def _export_investment_memo(
        self,
        artifact: Dict[str, Any],
        run_metadata: Dict[str, Any]
    ) -> Tuple[bytes, str, str]:
        """
        Export Investment Memo with special formatting matching InvestmentMemoView.

        Data Structure (from InvestmentMemoView):
        - company_overview: {company_name, industry}
        - sections: [{heading, content}]
        - financials: {...}
        - risks: [{risk, ...}]
        - opportunities: [...]
        - management: {summary, strengths[], gaps[]}
        - esg: {factors[], overall}
        - next_steps: [...]
        - inconsistencies: [...]
        """
        self.create_document()

        # Extract data
        data = artifact.get('parsed') or artifact

        company_name = 'Investment Memo'
        industry = None

        if data.get('company_overview'):
            company_name = data['company_overview'].get('company_name') or company_name
            industry = data['company_overview'].get('industry')

        # Cover Page
        self.add_title(company_name)
        self.add_title("Investment Memo")

        if industry:
            para = self.add_paragraph(industry)
            para.alignment = 1  # Center alignment

        # Metadata
        date_str = datetime.now().strftime('%B %d, %Y')
        if run_metadata.get('created_at'):
            try:
                date_str = run_metadata['created_at'].strftime('%B %d, %Y') if hasattr(run_metadata['created_at'], 'strftime') else date_str
            except:
                pass

        self.add_paragraph(f"Generated: {date_str}", bold=True)

        if run_metadata.get('latency_ms'):
            latency_s = run_metadata['latency_ms'] / 1000
            self.add_paragraph(f"Processing Time: {latency_s:.1f}s")

        if run_metadata.get('cost_usd'):
            self.add_paragraph(f"Cost: ${run_metadata['cost_usd']:.3f}")

        self.add_divider()

        # Sections (main content with markdown)
        if data.get('sections') and isinstance(data['sections'], list):
            for section in data['sections']:
                if section.get('heading'):
                    self.add_heading(section['heading'], level=1)

                if section.get('content'):
                    # Parse markdown content
                    self.add_markdown_content(section['content'])

        # Financials
        if data.get('financials'):
            self.add_heading("Financial Overview", level=1)
            self._add_financials(data['financials'], data.get('currency', 'USD'))

        # Risks
        if data.get('risks') and isinstance(data['risks'], list) and len(data['risks']) > 0:
            self.add_heading("Risk Analysis", level=1)
            for risk in data['risks']:
                risk_text = risk.get('risk') or risk.get('description') or str(risk) if isinstance(risk, dict) else str(risk)
                self.add_paragraph(f"⚠️ {risk_text}")

        # Opportunities
        if data.get('opportunities') and isinstance(data['opportunities'], list) and len(data['opportunities']) > 0:
            self.add_heading("Opportunities", level=1)
            for i, opp in enumerate(data['opportunities'], 1):
                opp_text = opp.get('opportunity') or opp.get('description') or str(opp) if isinstance(opp, dict) else str(opp)
                para = self.doc.add_paragraph(style='List Number')
                para.add_run(opp_text)

        # Management & Culture
        if data.get('management'):
            self.add_heading("Management & Culture", level=1)
            mgmt = data['management']

            if mgmt.get('summary'):
                self.add_paragraph(mgmt['summary'])

            if mgmt.get('strengths') and isinstance(mgmt['strengths'], list):
                self.add_heading("Strengths", level=2)
                for strength in mgmt['strengths']:
                    para = self.doc.add_paragraph(style='List Bullet')
                    para.add_run(str(strength))

            if mgmt.get('gaps') and isinstance(mgmt['gaps'], list):
                self.add_heading("Gaps", level=2)
                for gap in mgmt['gaps']:
                    para = self.doc.add_paragraph(style='List Bullet')
                    para.add_run(str(gap))

        # ESG Snapshot
        if data.get('esg'):
            self.add_heading("ESG Snapshot", level=1)
            esg = data['esg']

            if esg.get('factors') and isinstance(esg['factors'], list):
                for factor in esg['factors']:
                    dimension = factor.get('dimension', 'Factor')
                    status = factor.get('status', 'N/A')
                    self.add_paragraph(f"{dimension}: {status}", bold=True)

            if esg.get('overall'):
                self.add_paragraph(esg['overall'])

        # Next Steps
        if data.get('next_steps') and isinstance(data['next_steps'], list) and len(data['next_steps']) > 0:
            self.add_heading("Next Steps", level=1)
            for i, step in enumerate(data['next_steps'], 1):
                step_text = step.get('step') or step.get('action') or str(step) if isinstance(step, dict) else str(step)
                para = self.doc.add_paragraph(style='List Number')
                para.add_run(step_text)

        # Inconsistencies
        if data.get('inconsistencies') and isinstance(data['inconsistencies'], list) and len(data['inconsistencies']) > 0:
            self.add_heading("Inconsistencies Found", level=1)
            for item in data['inconsistencies']:
                item_text = item.get('inconsistency') or item.get('description') or str(item) if isinstance(item, dict) else str(item)
                self.add_paragraph(f"⚠️ {item_text}")

        # Footer
        self.add_divider()
        self.add_footer_text("This is a confidential document prepared for investment evaluation purposes.")
        self.add_footer_text("Generated using AI-powered workflow analysis from document intelligence.")
        self.add_footer_text("Generated by Sand Cloud Document Intelligence")

        if run_metadata.get('id'):
            self.add_footer_text(f"Run ID: {run_metadata['id']}")

        # Generate filename
        filename = self.sanitize_filename(f"{company_name}_Investment_Memo.docx")
        content = self.save_to_bytes()

        return (
            content,
            filename,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    def _add_financials(self, financials: Dict[str, Any], currency: str):
        """Add financials section with formatting."""
        for key, value in financials.items():
            if value is None or value == '':
                continue

            # Format key name
            key_display = key.replace('_', ' ').title()

            # Format value
            if isinstance(value, (int, float)):
                # Check if it's currency or percentage
                key_lower = key.lower()
                if any(term in key_lower for term in ['revenue', 'cost', 'profit', 'price', 'debt', 'equity']):
                    self.add_paragraph(f"{key_display}: {currency} {value:,.0f}")
                elif any(term in key_lower for term in ['margin', 'rate', 'percent', '%']):
                    self.add_paragraph(f"{key_display}: {value}%")
                else:
                    self.add_paragraph(f"{key_display}: {value:,}")
            elif isinstance(value, dict):
                # Nested dict - show as JSON or key-value
                self.add_heading(key_display, level=2)
                for k, v in value.items():
                    k_display = k.replace('_', ' ').title()
                    self.add_paragraph(f"{k_display}: {v}")
            elif isinstance(value, list):
                self.add_paragraph(f"{key_display}: {', '.join(str(v) for v in value)}")
            else:
                self.add_paragraph(f"{key_display}: {value}")

    def _export_generic_workflow(
        self,
        artifact: Dict[str, Any],
        run_metadata: Dict[str, Any]
    ) -> Tuple[bytes, str, str]:
        """
        Export generic workflow with markdown processing.

        Handles:
        - sections: [{heading, content}]
        - flat object: {key: value}
        - string: raw markdown
        """
        self.create_document()

        workflow_name = run_metadata.get('workflow_name', 'Workflow')
        date_str = datetime.now().strftime('%B %d, %Y')

        # Cover page
        self.add_title(workflow_name)
        self.add_title("Workflow Analysis Report")

        self.add_paragraph(f"Generated: {date_str}", bold=True)

        if run_metadata.get('status') == 'completed':
            self.add_paragraph("✓ Completed", bold=True)

        self.add_divider()

        # Extract data
        data = artifact.get('parsed') or artifact

        # Handle structured sections array
        if isinstance(data, dict) and data.get('sections') and isinstance(data['sections'], list):
            for section in data['sections']:
                if section.get('heading'):
                    self.add_heading(section['heading'], level=1)
                if section.get('content'):
                    self.add_markdown_content(section['content'])

        # Handle flat object format
        elif isinstance(data, dict):
            for key, value in data.items():
                # Skip metadata fields
                if key in ['metadata', 'summary', 'created_at']:
                    continue

                # Add section heading
                heading = key.replace('_', ' ').title()
                self.add_heading(heading, level=1)

                # Add content based on type
                if isinstance(value, str):
                    self.add_markdown_content(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            para = self.doc.add_paragraph(style='List Bullet')
                            para.add_run(item)
                        elif isinstance(item, dict):
                            self._add_dict_as_key_value(item)
                elif isinstance(value, dict):
                    self._add_dict_as_key_value(value)
                else:
                    self.add_paragraph(str(value))

        # Handle string format
        elif isinstance(data, str):
            self.add_markdown_content(data)

        # Footer
        self.add_divider()
        self.add_footer_text("Generated by Sand Cloud Document Intelligence")

        if run_metadata.get('id'):
            self.add_footer_text(f"Run ID: {run_metadata['id']}")

        if run_metadata.get('duration_seconds'):
            self.add_footer_text(f"Processing Time: {run_metadata['duration_seconds']}s")

        # Generate filename
        filename = self.sanitize_filename(f"{workflow_name}_Report.docx")
        content = self.save_to_bytes()

        return (
            content,
            filename,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    def _add_dict_as_key_value(self, data: Dict[str, Any]):
        """Add dictionary as key-value pairs."""
        for key, value in data.items():
            if value is None or value == '':
                continue

            key_display = key.replace('_', ' ').title()

            if isinstance(value, dict):
                # Nested dict
                import json
                value_str = json.dumps(value, indent=2)
                self.add_paragraph(f"{key_display}: {value_str}")
            elif isinstance(value, list):
                value_str = ', '.join(str(v) for v in value)
                self.add_paragraph(f"{key_display}: {value_str}")
            else:
                self.add_paragraph(f"{key_display}: {value}")

    def export_to_excel(
        self,
        artifact: Dict[str, Any],
        run_metadata: Dict[str, Any]
    ) -> Tuple[bytes, str, str]:
        """
        Export workflow to Excel (reuses existing to_xlsx_bytes logic).

        Args:
            artifact: Workflow artifact data
            run_metadata: Run metadata

        Returns:
            Tuple of (bytes, filename, content_type)
        """
        # Reuse the existing Excel export from exporter.py
        from app.services.exporter import to_xlsx_bytes

        data = artifact.get('parsed') or artifact
        content, filename = to_xlsx_bytes(data)

        return (
            content,
            filename,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
