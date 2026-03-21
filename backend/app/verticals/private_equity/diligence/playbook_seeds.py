"""System playbooks for PE diligence clause extraction.

Provides SYSTEM_PLAYBOOKS — the 15 built-in baseline analysis playbooks seeded on startup.
Each playbook defines:
  - slug/title/description
  - applicable_doc_types: list of doc type strings this playbook should run against;
    None = run against all doc types (backward compat)
  - clause_types: list of clause_type strings this playbook covers
  - prompt_template: LLM extraction prompt (uses {candidate_chunks} placeholder)
  - output_schema: JSON schema for extracted_fields per clause
  - baseline analysis instruction text derived from the seeded metadata
"""

from __future__ import annotations

from typing import Dict, List

from app.verticals.private_equity.diligence.doc_types import validate_doc_type_list

SYSTEM_PLAYBOOKS: List[dict] = [
    # ── 1. Change of Control & Assignment ─────────────────────────────────────
    {
        "slug": "change_of_control",
        "title": "Change of Control & Assignment",
        "description": (
            "Identifies change-of-control triggers, assignment/consent requirements, "
            "drag-along/tag-along provisions, and novation clauses across the deal."
        ),
        "applicable_doc_types": [
            "purchase_agreement", "merger_agreement", "legal_contract",
            "customer_contract", "vendor_contract", "ip_license",
            "shareholder_agreement", "employment_agreement", "disclosure_schedule",
        ],
        "clause_types": [
            "change_of_control",
            "assignment_consent",
            "novation",
            "drag_along",
            "tag_along",
        ],
        "prompt_template": (
            "You are a PE diligence lawyer. Extract all change-of-control, assignment, "
            "and novation clauses from the following document excerpts. "
            "For each clause found, return a JSON object with these fields:\n"
            "  - clause_type: one of [change_of_control, assignment_consent, novation, drag_along, tag_along]\n"
            "  - triggers: list of strings describing what events trigger this clause\n"
            "  - consent_required: boolean — does counterparty consent need to be obtained?\n"
            "  - consent_parties: list of parties whose consent is required\n"
            "  - consequences: string — what happens if triggered (e.g., termination, acceleration)\n"
            "  - threshold: string or null — ownership percentage or other numeric threshold\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1 how confident you are this is a genuine clause (not boilerplate)\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "triggers": {"type": "array", "items": {"type": "string"}, "title": "Triggers"},
                    "consent_required": {"type": "boolean", "title": "Consent Required"},
                    "consent_parties": {"type": "array", "items": {"type": "string"}, "title": "Consent Parties"},
                    "consequences": {"type": "string", "title": "Consequences"},
                    "threshold": {"type": ["string", "null"], "title": "Threshold"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 2. Customer Concentration & Revenue ───────────────────────────────────
    {
        "slug": "customer_concentration",
        "title": "Customer Concentration & Revenue",
        "description": (
            "Extracts customer concentration risk, MFN pricing, exclusivity, "
            "revenue share, and termination-for-convenience provisions."
        ),
        "applicable_doc_types": [
            "purchase_agreement", "merger_agreement", "legal_contract",
            "customer_contract", "financial_statement", "disclosure_schedule",
        ],
        "clause_types": [
            "customer_contract",
            "revenue_share",
            "exclusivity",
            "mfn_pricing",
            "termination",
        ],
        "prompt_template": (
            "You are a PE diligence analyst. Extract customer and revenue-related clauses "
            "from the following document excerpts. "
            "For each clause, return a JSON object with:\n"
            "  - clause_type: one of [customer_contract, revenue_share, exclusivity, mfn_pricing, termination]\n"
            "  - counterparty: string — name of the customer/counterparty if mentioned\n"
            "  - revenue_share_pct: number or null — percentage if revenue share\n"
            "  - exclusivity_scope: string or null — geographic/product scope of exclusivity\n"
            "  - mfn_applies_to: string or null — what the MFN clause applies to\n"
            "  - termination_notice_days: integer or null — notice period for termination\n"
            "  - termination_for_convenience: boolean — can either party terminate at will?\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "counterparty": {"type": ["string", "null"], "title": "Counterparty"},
                    "revenue_share_pct": {"type": ["number", "null"], "title": "Revenue Share (%)"},
                    "exclusivity_scope": {"type": ["string", "null"], "title": "Exclusivity Scope"},
                    "mfn_applies_to": {"type": ["string", "null"], "title": "MFN Applies To"},
                    "termination_notice_days": {"type": ["integer", "null"], "title": "Termination Notice (days)"},
                    "termination_for_convenience": {"type": ["boolean", "null"], "title": "Termination for Convenience"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 3. Debt & Covenant Analysis ───────────────────────────────────────────
    {
        "slug": "debt_covenants",
        "title": "Debt & Covenant Analysis",
        "description": (
            "Extracts debt covenants, leverage ratios, interest coverage minimums, "
            "events of default, and prepayment provisions."
        ),
        "applicable_doc_types": [
            "purchase_agreement", "financial_statement", "legal_contract",
        ],
        "clause_types": [
            "debt_covenant",
            "leverage_ratio",
            "interest_coverage",
            "event_of_default",
            "prepayment",
        ],
        "prompt_template": (
            "You are a PE diligence analyst specializing in debt structures. "
            "Extract all debt and covenant-related clauses from the following excerpts. "
            "For each clause, return a JSON object with:\n"
            "  - clause_type: one of [debt_covenant, leverage_ratio, interest_coverage, event_of_default, prepayment]\n"
            "  - covenant_type: string — financial, maintenance, incurrence, or reporting\n"
            "  - threshold_value: number or null — numeric threshold (e.g., 4.0 for 4.0x leverage)\n"
            "  - threshold_unit: string or null — unit (e.g., 'x', '%', 'USD')\n"
            "  - measurement_period: string or null — quarterly, annually, LTM, etc.\n"
            "  - cure_period_days: integer or null — days to cure a breach\n"
            "  - prepayment_penalty_pct: number or null — penalty percentage if prepayment\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "covenant_type": {"type": ["string", "null"], "title": "Covenant Type"},
                    "threshold_value": {"type": ["number", "null"], "title": "Threshold Value"},
                    "threshold_unit": {"type": ["string", "null"], "title": "Threshold Unit"},
                    "measurement_period": {"type": ["string", "null"], "title": "Measurement Period"},
                    "cure_period_days": {"type": ["integer", "null"], "title": "Cure Period (days)"},
                    "prepayment_penalty_pct": {"type": ["number", "null"], "title": "Prepayment Penalty (%)"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 4. IP & Technology Ownership ──────────────────────────────────────────
    {
        "slug": "ip_ownership",
        "title": "IP & Technology Ownership",
        "description": (
            "Identifies IP assignment, license grant/scope, non-compete, "
            "non-solicitation, and work-for-hire provisions."
        ),
        "applicable_doc_types": [
            "purchase_agreement", "merger_agreement", "legal_contract",
            "ip_license", "employment_agreement", "disclosure_schedule",
        ],
        "clause_types": [
            "ip_assignment",
            "license_terms",
            "non_compete",
            "non_solicit",
        ],
        "prompt_template": (
            "You are a PE diligence lawyer specializing in IP. "
            "Extract IP and technology ownership clauses from the following excerpts. "
            "For each clause, return a JSON object with:\n"
            "  - clause_type: one of [ip_assignment, license_terms, non_compete, non_solicit]\n"
            "  - ip_category: string — patent, trademark, copyright, trade_secret, software, or general\n"
            "  - assignment_direction: string or null — 'to_company' or 'from_company'\n"
            "  - license_scope: string or null — exclusive, non-exclusive, field-of-use\n"
            "  - license_territory: string or null — geographic scope\n"
            "  - restriction_period_months: integer or null — duration of non-compete/non-solicit\n"
            "  - restriction_scope: string or null — geographic/activity scope of restriction\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "ip_category": {"type": ["string", "null"], "title": "IP Category"},
                    "assignment_direction": {"type": ["string", "null"], "title": "Assignment Direction"},
                    "license_scope": {"type": ["string", "null"], "title": "License Scope"},
                    "license_territory": {"type": ["string", "null"], "title": "License Territory"},
                    "restriction_period_months": {"type": ["integer", "null"], "title": "Restriction Period (months)"},
                    "restriction_scope": {"type": ["string", "null"], "title": "Restriction Scope"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 5. Key Employee & Compensation ────────────────────────────────────────
    {
        "slug": "employment",
        "title": "Key Employee & Compensation",
        "description": (
            "Extracts employment term, severance, non-compete, equity vesting, "
            "and change-of-control compensation provisions for key personnel."
        ),
        "applicable_doc_types": [
            "employment_agreement", "purchase_agreement", "shareholder_agreement",
        ],
        "clause_types": [
            "employment_term",
            "severance",
            "non_compete",
            "equity_vesting",
            "change_of_control",
        ],
        "prompt_template": (
            "You are a PE diligence analyst specializing in management compensation. "
            "Extract key employee and compensation clauses from the following excerpts. "
            "For each clause, return a JSON object with:\n"
            "  - clause_type: one of [employment_term, severance, non_compete, equity_vesting, change_of_control]\n"
            "  - employee_role: string or null — title/role of the key employee\n"
            "  - term_months: integer or null — contract term in months\n"
            "  - severance_months: integer or null — months of severance pay\n"
            "  - severance_trigger: string or null — what triggers severance (termination without cause, CoC, etc.)\n"
            "  - equity_type: string or null — options, RSUs, profits interest, etc.\n"
            "  - vesting_period_months: integer or null — total vesting period\n"
            "  - vesting_cliff_months: integer or null — cliff period in months\n"
            "  - acceleration_trigger: string or null — single-trigger or double-trigger\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "employee_role": {"type": ["string", "null"], "title": "Employee Role"},
                    "term_months": {"type": ["integer", "null"], "title": "Term (months)"},
                    "severance_months": {"type": ["integer", "null"], "title": "Severance (months)"},
                    "severance_trigger": {"type": ["string", "null"], "title": "Severance Trigger"},
                    "equity_type": {"type": ["string", "null"], "title": "Equity Type"},
                    "vesting_period_months": {"type": ["integer", "null"], "title": "Vesting Period (months)"},
                    "vesting_cliff_months": {"type": ["integer", "null"], "title": "Vesting Cliff (months)"},
                    "acceleration_trigger": {"type": ["string", "null"], "title": "Acceleration Trigger"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 6. SPA Core Terms ─────────────────────────────────────────────────────
    {
        "slug": "spa_core",
        "title": "SPA Core Terms",
        "description": (
            "Extracts representations & warranties, indemnification caps, MAC/MAE clauses, "
            "closing conditions, purchase price mechanics, earnout provisions, basket/deductible "
            "structures, and survival periods from SPAs and acquisition agreements."
        ),
        "applicable_doc_types": [
            "purchase_agreement", "merger_agreement", "disclosure_schedule",
        ],
        "clause_types": [
            "representations_warranties",
            "indemnification_cap",
            "material_adverse_change",
            "closing_conditions",
            "purchase_price_adjustment",
            "earnout_mechanics",
            "basket_deductible",
            "survival_period",
        ],
        "prompt_template": (
            "You are a PE M&A lawyer reviewing a Share Purchase Agreement or acquisition agreement. "
            "Extract the core deal terms from the following document excerpts. "
            "For each clause found, return a JSON object with these fields:\n"
            "  - clause_type: one of [representations_warranties, indemnification_cap, material_adverse_change, closing_conditions, purchase_price_adjustment, earnout_mechanics, basket_deductible, survival_period]\n"
            "  - scope: string or null — scope/category (e.g., 'fundamental reps', 'general reps', 'tax reps')\n"
            "  - cap_amount: number or null — indemnification cap in USD (absolute dollar amount)\n"
            "  - cap_pct_ev: number or null — indemnification cap as % of enterprise/deal value if stated\n"
            "  - basket_amount: number or null — basket/deductible threshold in USD\n"
            "  - basket_type: string or null — 'tipping' or 'true_deductible'\n"
            "  - survival_months: integer or null — survival period in months\n"
            "  - mac_carveouts: list of strings — specific MAC/MAE carveouts listed\n"
            "  - adjustment_mechanism: string or null — 'locked_box', 'completion_accounts', or 'working_capital'\n"
            "  - adjustment_reference_date: string or null — reference date for locked box or working capital peg\n"
            "  - earnout_period_months: integer or null — earnout measurement period in months\n"
            "  - earnout_metric: string or null — metric triggering earnout (revenue, EBITDA, gross profit, etc.)\n"
            "  - earnout_cap: number or null — maximum earnout payment in USD\n"
            "  - closing_condition_party: string or null — 'buyer', 'seller', or 'mutual'\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Only include clauses you actually found. If no relevant clauses, return {\"clauses\": []}.\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "scope": {"type": ["string", "null"], "title": "Scope"},
                    "cap_amount": {"type": ["number", "null"], "title": "Indemnification Cap ($)"},
                    "cap_pct_ev": {"type": ["number", "null"], "title": "Cap (% of EV)"},
                    "basket_amount": {"type": ["number", "null"], "title": "Basket Amount ($)"},
                    "basket_type": {"type": ["string", "null"], "title": "Basket Type"},
                    "survival_months": {"type": ["integer", "null"], "title": "Survival Period (months)"},
                    "mac_carveouts": {"type": "array", "items": {"type": "string"}, "title": "MAC Carveouts"},
                    "adjustment_mechanism": {"type": ["string", "null"], "title": "Price Adjustment Mechanism"},
                    "adjustment_reference_date": {"type": ["string", "null"], "title": "Adjustment Reference Date"},
                    "earnout_period_months": {"type": ["integer", "null"], "title": "Earnout Period (months)"},
                    "earnout_metric": {"type": ["string", "null"], "title": "Earnout Metric"},
                    "earnout_cap": {"type": ["number", "null"], "title": "Earnout Cap ($)"},
                    "closing_condition_party": {"type": ["string", "null"], "title": "Closing Condition Party"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 7. Litigation & Contingent Liability ──────────────────────────────────
    {
        "slug": "litigation",
        "title": "Litigation & Contingent Liability",
        "description": (
            "Identifies pending/threatened litigation, indemnity obligations, settlement "
            "restrictions, and contingent liabilities disclosed in the deal documents."
        ),
        "applicable_doc_types": [
            "purchase_agreement", "legal_contract", "disclosure_schedule",
        ],
        "clause_types": [
            "litigation_disclosure",
            "indemnity_obligation",
            "settlement_restriction",
            "contingent_liability",
        ],
        "prompt_template": (
            "You are a PE diligence lawyer. Extract all litigation, indemnity, and contingent "
            "liability disclosures from the following document excerpts. "
            "For each item found, return a JSON object with:\n"
            "  - clause_type: one of [litigation_disclosure, indemnity_obligation, settlement_restriction, contingent_liability]\n"
            "  - parties_involved: list of strings — plaintiff/defendant or indemnifying/indemnified parties\n"
            "  - amount_in_dispute: number or null — USD amount at risk\n"
            "  - status: string or null — pending, threatened, settled, resolved\n"
            "  - settlement_restriction: string or null — any restriction on settling (e.g., requires buyer consent)\n"
            "  - indemnity_cap: number or null — indemnity cap in USD if stated\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "parties_involved": {"type": "array", "items": {"type": "string"}, "title": "Parties Involved"},
                    "amount_in_dispute": {"type": ["number", "null"], "title": "Amount in Dispute ($)"},
                    "status": {"type": ["string", "null"], "title": "Status"},
                    "settlement_restriction": {"type": ["string", "null"], "title": "Settlement Restriction"},
                    "indemnity_cap": {"type": ["number", "null"], "title": "Indemnity Cap ($)"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 8. Tax Exposure & Structure ───────────────────────────────────────────
    {
        "slug": "tax_exposure",
        "title": "Tax Exposure & Structure",
        "description": (
            "Extracts tax representations, tax indemnities, NOL carryforwards, "
            "transfer pricing policies, and tax step-up provisions."
        ),
        "applicable_doc_types": [
            "purchase_agreement", "financial_statement", "tax_document", "disclosure_schedule",
        ],
        "clause_types": [
            "tax_representation",
            "tax_indemnity",
            "nol_carryforward",
            "transfer_pricing",
            "tax_step_up",
        ],
        "prompt_template": (
            "You are a PE tax diligence specialist. Extract tax-related clauses and disclosures "
            "from the following document excerpts. "
            "For each item found, return a JSON object with:\n"
            "  - clause_type: one of [tax_representation, tax_indemnity, nol_carryforward, transfer_pricing, tax_step_up]\n"
            "  - tax_period_covered: string or null — years or period covered by tax rep\n"
            "  - indemnity_cap: number or null — tax indemnity cap in USD\n"
            "  - indemnity_period_years: integer or null — years the tax indemnity survives\n"
            "  - nol_amount: number or null — NOL carryforward amount in USD\n"
            "  - step_up_amount: number or null — tax step-up amount in USD\n"
            "  - transfer_pricing_policy: string or null — arm's-length description\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "tax_period_covered": {"type": ["string", "null"], "title": "Tax Period Covered"},
                    "indemnity_cap": {"type": ["number", "null"], "title": "Indemnity Cap ($)"},
                    "indemnity_period_years": {"type": ["integer", "null"], "title": "Indemnity Period (years)"},
                    "nol_amount": {"type": ["number", "null"], "title": "NOL Amount ($)"},
                    "step_up_amount": {"type": ["number", "null"], "title": "Step-Up Amount ($)"},
                    "transfer_pricing_policy": {"type": ["string", "null"], "title": "Transfer Pricing Policy"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 9. Material Contracts — Supplier & Vendor ─────────────────────────────
    {
        "slug": "supplier_contracts",
        "title": "Material Contracts — Supplier & Vendor",
        "description": (
            "Extracts supplier concentration risk, sole-source dependencies, "
            "minimum purchase commitments, and price escalation clauses."
        ),
        "applicable_doc_types": [
            "legal_contract", "purchase_agreement", "disclosure_schedule",
        ],
        "clause_types": [
            "supplier_concentration",
            "sole_source",
            "minimum_purchase_commitment",
            "price_escalation",
        ],
        "prompt_template": (
            "You are a PE operations diligence analyst. Extract supplier and vendor contract "
            "clauses from the following document excerpts. "
            "For each clause found, return a JSON object with:\n"
            "  - clause_type: one of [supplier_concentration, sole_source, minimum_purchase_commitment, price_escalation]\n"
            "  - supplier_name: string or null — name of the supplier/vendor\n"
            "  - contract_value_usd: number or null — total contract value\n"
            "  - minimum_commitment_usd: number or null — minimum purchase/spend commitment\n"
            "  - commitment_period_months: integer or null — period of the commitment\n"
            "  - price_escalation_pct: number or null — annual price escalation percentage\n"
            "  - price_escalation_cap: string or null — cap on escalation (CPI-linked, fixed, etc.)\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "supplier_name": {"type": ["string", "null"], "title": "Supplier Name"},
                    "contract_value_usd": {"type": ["number", "null"], "title": "Contract Value ($)"},
                    "minimum_commitment_usd": {"type": ["number", "null"], "title": "Minimum Commitment ($)"},
                    "commitment_period_months": {"type": ["integer", "null"], "title": "Commitment Period (months)"},
                    "price_escalation_pct": {"type": ["number", "null"], "title": "Price Escalation (%)"},
                    "price_escalation_cap": {"type": ["string", "null"], "title": "Price Escalation Cap (%)"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 10. Regulatory & Licensing ────────────────────────────────────────────
    {
        "slug": "regulatory_licensing",
        "title": "Regulatory & Licensing",
        "description": (
            "Extracts required regulatory approvals, license requirements, "
            "government contract terms, and export control restrictions."
        ),
        "applicable_doc_types": [
            "regulatory_filing", "legal_contract", "disclosure_schedule", "purchase_agreement",
        ],
        "clause_types": [
            "regulatory_approval",
            "license_requirement",
            "government_contract",
            "export_control",
        ],
        "prompt_template": (
            "You are a PE regulatory diligence specialist. Extract regulatory, licensing, "
            "and government contract clauses from the following document excerpts. "
            "For each item found, return a JSON object with:\n"
            "  - clause_type: one of [regulatory_approval, license_requirement, government_contract, export_control]\n"
            "  - regulator_or_agency: string or null — name of the regulatory body or agency\n"
            "  - license_type: string or null — type of license or permit\n"
            "  - approval_condition: string or null — what must happen to obtain approval\n"
            "  - government_contract_value: number or null — government contract value in USD\n"
            "  - export_jurisdiction: string or null — countries/regimes subject to export control\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "regulator_or_agency": {"type": ["string", "null"], "title": "Regulator / Agency"},
                    "license_type": {"type": ["string", "null"], "title": "License Type"},
                    "approval_condition": {"type": ["string", "null"], "title": "Approval Condition"},
                    "government_contract_value": {"type": ["number", "null"], "title": "Government Contract Value ($)"},
                    "export_jurisdiction": {"type": ["string", "null"], "title": "Export Jurisdiction"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 11. Data Privacy & Cybersecurity ──────────────────────────────────────
    {
        "slug": "data_privacy",
        "title": "Data Privacy & Cybersecurity",
        "description": (
            "Extracts data processing agreement terms, breach notification obligations, "
            "GDPR/CCPA compliance requirements, and data retention schedules."
        ),
        "applicable_doc_types": [
            "legal_contract", "policy_document", "disclosure_schedule",
        ],
        "clause_types": [
            "data_processing_agreement",
            "breach_notification",
            "gdpr_compliance",
            "data_retention",
        ],
        "prompt_template": (
            "You are a PE technology diligence analyst specializing in data privacy. "
            "Extract data privacy and cybersecurity clauses from the following document excerpts. "
            "For each clause found, return a JSON object with:\n"
            "  - clause_type: one of [data_processing_agreement, breach_notification, gdpr_compliance, data_retention]\n"
            "  - regulation: string or null — GDPR, CCPA, HIPAA, or other applicable regulation\n"
            "  - data_categories: list of strings — types of personal data covered\n"
            "  - breach_notification_hours: integer or null — hours to notify after a breach\n"
            "  - retention_period_months: integer or null — data retention period\n"
            "  - dpa_controller_processor: string or null — 'controller' or 'processor' role\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "regulation": {"type": ["string", "null"], "title": "Regulation"},
                    "data_categories": {"type": "array", "items": {"type": "string"}, "title": "Data Categories"},
                    "breach_notification_hours": {"type": ["integer", "null"], "title": "Breach Notification (hours)"},
                    "retention_period_months": {"type": ["integer", "null"], "title": "Retention Period (months)"},
                    "dpa_controller_processor": {"type": ["string", "null"], "title": "DPA Role (Controller/Processor)"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 12. Environmental & ESG ───────────────────────────────────────────────
    {
        "slug": "environmental_esg",
        "title": "Environmental & ESG",
        "description": (
            "Identifies known environmental liabilities, remediation obligations, "
            "ESG covenants, and carbon/emissions commitments."
        ),
        "applicable_doc_types": [
            "disclosure_schedule", "legal_contract", "regulatory_filing", "purchase_agreement",
        ],
        "clause_types": [
            "environmental_liability",
            "remediation_obligation",
            "esg_covenant",
            "carbon_commitment",
        ],
        "prompt_template": (
            "You are a PE environmental diligence specialist. Extract environmental and ESG "
            "clauses and disclosures from the following document excerpts. "
            "For each item found, return a JSON object with:\n"
            "  - clause_type: one of [environmental_liability, remediation_obligation, esg_covenant, carbon_commitment]\n"
            "  - liability_description: string or null — description of the environmental issue\n"
            "  - estimated_cost_usd: number or null — estimated remediation/liability cost\n"
            "  - regulatory_body: string or null — EPA, state agency, or other authority involved\n"
            "  - esg_metric: string or null — specific ESG metric or target\n"
            "  - carbon_target: string or null — emissions reduction target (e.g., 'net zero by 2030')\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "liability_description": {"type": ["string", "null"], "title": "Liability Description"},
                    "estimated_cost_usd": {"type": ["number", "null"], "title": "Estimated Cost ($)"},
                    "regulatory_body": {"type": ["string", "null"], "title": "Regulatory Body"},
                    "esg_metric": {"type": ["string", "null"], "title": "ESG Metric"},
                    "carbon_target": {"type": ["string", "null"], "title": "Carbon Target"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 13. Insurance Coverage ────────────────────────────────────────────────
    {
        "slug": "insurance_coverage",
        "title": "Insurance Coverage",
        "description": (
            "Extracts R&W insurance terms, coverage gaps, tail coverage periods, "
            "and notable exclusion carve-outs."
        ),
        "applicable_doc_types": [
            "insurance_document", "purchase_agreement", "disclosure_schedule",
        ],
        "clause_types": [
            "coverage_gap",
            "rep_warranty_insurance",
            "tail_coverage",
            "exclusion_carveout",
        ],
        "prompt_template": (
            "You are a PE deal lawyer specializing in insurance. Extract insurance "
            "coverage clauses and terms from the following document excerpts. "
            "For each item found, return a JSON object with:\n"
            "  - clause_type: one of [coverage_gap, rep_warranty_insurance, tail_coverage, exclusion_carveout]\n"
            "  - insurer: string or null — name of the insurance carrier\n"
            "  - coverage_limit_usd: number or null — policy limit in USD\n"
            "  - retention_usd: number or null — retention/deductible in USD\n"
            "  - tail_period_years: integer or null — tail coverage period in years\n"
            "  - notable_exclusions: list of strings — specific exclusions or carve-outs\n"
            "  - coverage_gap_description: string or null — description of gap in coverage\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "insurer": {"type": ["string", "null"], "title": "Insurer"},
                    "coverage_limit_usd": {"type": ["number", "null"], "title": "Coverage Limit ($)"},
                    "retention_usd": {"type": ["number", "null"], "title": "Retention ($)"},
                    "tail_period_years": {"type": ["integer", "null"], "title": "Tail Period (years)"},
                    "notable_exclusions": {"type": "array", "items": {"type": "string"}, "title": "Notable Exclusions"},
                    "coverage_gap_description": {"type": ["string", "null"], "title": "Coverage Gap Description"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 14. Related Party Transactions ────────────────────────────────────────
    {
        "slug": "related_party_transactions",
        "title": "Related Party Transactions",
        "description": (
            "Identifies affiliate transactions, management fees, officer loans, "
            "and insider payments that may need unwinding post-close."
        ),
        "applicable_doc_types": [
            "purchase_agreement", "financial_statement", "disclosure_schedule",
        ],
        "clause_types": [
            "related_party_transaction",
            "affiliate_payment",
            "management_fee",
            "loan_to_officer",
        ],
        "prompt_template": (
            "You are a PE diligence analyst reviewing related party transactions. "
            "Extract related party and affiliate transaction disclosures from the following excerpts. "
            "For each item found, return a JSON object with:\n"
            "  - clause_type: one of [related_party_transaction, affiliate_payment, management_fee, loan_to_officer]\n"
            "  - related_party: string or null — name or description of the related party\n"
            "  - transaction_amount_usd: number or null — transaction value in USD\n"
            "  - annual_amount_usd: number or null — annual recurring amount if applicable\n"
            "  - arm_length_confirmed: boolean or null — whether arm's-length confirmed\n"
            "  - ongoing_obligation: boolean — whether this continues post-close\n"
            "  - termination_required: boolean — whether buyer requires termination at closing\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "related_party": {"type": ["string", "null"], "title": "Related Party"},
                    "transaction_amount_usd": {"type": ["number", "null"], "title": "Transaction Amount ($)"},
                    "annual_amount_usd": {"type": ["number", "null"], "title": "Annual Amount ($)"},
                    "arm_length_confirmed": {"type": ["boolean", "null"], "title": "Arm's Length Confirmed"},
                    "ongoing_obligation": {"type": ["boolean", "null"], "title": "Ongoing Obligation"},
                    "termination_required": {"type": ["boolean", "null"], "title": "Termination Required"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    # ── 15. Governance & Equity Structure ─────────────────────────────────────
    {
        "slug": "governance_equity",
        "title": "Governance & Equity Structure",
        "description": (
            "Extracts voting rights, board composition, anti-dilution provisions, "
            "and liquidation preference waterfall from charter and shareholder documents."
        ),
        "applicable_doc_types": [
            "charter_document", "purchase_agreement", "shareholder_agreement",
        ],
        "clause_types": [
            "voting_rights",
            "board_composition",
            "anti_dilution",
            "liquidation_preference",
        ],
        "prompt_template": (
            "You are a PE deal lawyer specializing in governance and equity structures. "
            "Extract governance and equity structure clauses from the following document excerpts. "
            "For each clause found, return a JSON object with:\n"
            "  - clause_type: one of [voting_rights, board_composition, anti_dilution, liquidation_preference]\n"
            "  - share_class: string or null — share class affected (e.g., 'Series A Preferred', 'Class B Common')\n"
            "  - voting_threshold: string or null — required vote threshold (e.g., '66.7%', 'supermajority')\n"
            "  - board_seats: integer or null — number of board seats assigned\n"
            "  - board_seat_holder: string or null — party holding the board seat\n"
            "  - anti_dilution_type: string or null — 'full_ratchet' or 'weighted_average'\n"
            "  - liquidation_multiple: number or null — liquidation preference multiple (e.g., 1.5 for 1.5x)\n"
            "  - participating: boolean or null — whether preferred participates after preference\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "share_class": {"type": ["string", "null"], "title": "Share Class"},
                    "voting_threshold": {"type": ["string", "null"], "title": "Voting Threshold"},
                    "board_seats": {"type": ["integer", "null"], "title": "Board Seats"},
                    "board_seat_holder": {"type": ["string", "null"], "title": "Board Seat Holder"},
                    "anti_dilution_type": {"type": ["string", "null"], "title": "Anti-Dilution Type"},
                    "liquidation_multiple": {"type": ["number", "null"], "title": "Liquidation Multiple"},
                    "participating": {"type": ["boolean", "null"], "title": "Participating Preferred"},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
]


def _validate_system_playbooks() -> None:
    for playbook in SYSTEM_PLAYBOOKS:
        slug = playbook.get("slug", "<unknown>")
        validate_doc_type_list(
            playbook.get("applicable_doc_types"),
            context=f"playbook:{slug}:applicable_doc_types",
        )


_validate_system_playbooks()


_ANALYSIS_INSTRUCTION_SKIP_FIELDS = {
    "clause_type",
    "raw_quote",
    "interpretation",
    "confidence",
}


def _humanize_field_name(field_name: str) -> str:
    return field_name.replace("_", " ")


def build_playbook_analysis_instruction(playbook: dict) -> str:
    """Build the concise per-doc analyzer instruction from the seeded playbook."""
    title = playbook.get("title") or playbook.get("slug") or "Playbook"
    description = (playbook.get("description") or "").strip()
    clause_types = [str(v) for v in (playbook.get("clause_types") or []) if v]
    output_properties = (
        (((playbook.get("output_schema") or {}).get("items") or {}).get("properties") or {})
    )
    structured_fields = [
        _humanize_field_name(field_name)
        for field_name in output_properties.keys()
        if field_name not in _ANALYSIS_INSTRUCTION_SKIP_FIELDS
    ]

    lines = [f"[{title}]"]
    if description:
        lines.append(f"Focus: {description}")
    if clause_types:
        lines.append(f"Prioritize clauses: {', '.join(clause_types)}.")
    if structured_fields:
        lines.append(
            "Capture key structured fields where present: "
            + ", ".join(structured_fields[:8])
            + "."
        )
    return "\n".join(lines)


SYSTEM_PLAYBOOKS_BY_SLUG: Dict[str, dict] = {
    playbook["slug"]: playbook for playbook in SYSTEM_PLAYBOOKS if playbook.get("slug")
}


def seed_system_playbooks(db) -> int:
    """Upsert all system playbooks. Returns the count inserted or updated.

    Safe to call on every startup — uses slug as idempotency key.
    Only updates fields if the playbook slug already exists.
    """
    from app.db_models_pe_diligence import PEDiligencePlaybook

    created = 0
    for pb_data in SYSTEM_PLAYBOOKS:
        slug = pb_data["slug"]
        existing = db.query(PEDiligencePlaybook).filter(PEDiligencePlaybook.slug == slug).first()
        if existing is None:
            pb = PEDiligencePlaybook(
                slug=slug,
                title=pb_data["title"],
                description=pb_data.get("description"),
                applicable_doc_types=pb_data.get("applicable_doc_types"),
                clause_types=pb_data.get("clause_types"),
                prompt_template=pb_data.get("prompt_template"),
                output_schema=pb_data.get("output_schema"),
                is_system=True,
            )
            db.add(pb)
            created += 1
        else:
            # Update mutable fields on existing playbook
            existing.title = pb_data["title"]
            existing.description = pb_data.get("description")
            existing.applicable_doc_types = pb_data.get("applicable_doc_types")
            existing.clause_types = pb_data.get("clause_types")
            existing.prompt_template = pb_data.get("prompt_template")
            existing.output_schema = pb_data.get("output_schema")
    db.commit()
    return created
