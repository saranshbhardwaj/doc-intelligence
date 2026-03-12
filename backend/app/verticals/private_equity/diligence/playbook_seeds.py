"""System playbooks for PE diligence clause extraction.

Provides SYSTEM_PLAYBOOKS — the 5 built-in investigation playbooks seeded on startup.
Each playbook defines:
  - slug/title/description
  - clause_types: list of clause_type strings this playbook covers
  - prompt_template: LLM extraction prompt (uses {candidate_chunks} placeholder)
  - output_schema: JSON schema for extracted_fields per clause
"""

from __future__ import annotations

from typing import List

SYSTEM_PLAYBOOKS: List[dict] = [
    {
        "slug": "change_of_control",
        "title": "Change of Control & Assignment",
        "description": (
            "Identifies change-of-control triggers, assignment/consent requirements, "
            "drag-along/tag-along provisions, and novation clauses across the deal."
        ),
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
                    "triggers": {"type": "array", "items": {"type": "string"}},
                    "consent_required": {"type": "boolean"},
                    "consent_parties": {"type": "array", "items": {"type": "string"}},
                    "consequences": {"type": "string"},
                    "threshold": {"type": ["string", "null"]},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    {
        "slug": "customer_concentration",
        "title": "Customer Concentration & Revenue",
        "description": (
            "Extracts customer concentration risk, MFN pricing, exclusivity, "
            "revenue share, and termination-for-convenience provisions."
        ),
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
                    "counterparty": {"type": ["string", "null"]},
                    "revenue_share_pct": {"type": ["number", "null"]},
                    "exclusivity_scope": {"type": ["string", "null"]},
                    "mfn_applies_to": {"type": ["string", "null"]},
                    "termination_notice_days": {"type": ["integer", "null"]},
                    "termination_for_convenience": {"type": ["boolean", "null"]},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    {
        "slug": "debt_covenants",
        "title": "Debt & Covenant Analysis",
        "description": (
            "Extracts debt covenants, leverage ratios, interest coverage minimums, "
            "events of default, and prepayment provisions."
        ),
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
                    "covenant_type": {"type": ["string", "null"]},
                    "threshold_value": {"type": ["number", "null"]},
                    "threshold_unit": {"type": ["string", "null"]},
                    "measurement_period": {"type": ["string", "null"]},
                    "cure_period_days": {"type": ["integer", "null"]},
                    "prepayment_penalty_pct": {"type": ["number", "null"]},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    {
        "slug": "ip_ownership",
        "title": "IP & Technology Ownership",
        "description": (
            "Identifies IP assignment, license grant/scope, non-compete, "
            "non-solicitation, and work-for-hire provisions."
        ),
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
                    "ip_category": {"type": ["string", "null"]},
                    "assignment_direction": {"type": ["string", "null"]},
                    "license_scope": {"type": ["string", "null"]},
                    "license_territory": {"type": ["string", "null"]},
                    "restriction_period_months": {"type": ["integer", "null"]},
                    "restriction_scope": {"type": ["string", "null"]},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    {
        "slug": "employment",
        "title": "Key Employee & Compensation",
        "description": (
            "Extracts employment term, severance, non-compete, equity vesting, "
            "and change-of-control compensation provisions for key personnel."
        ),
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
                    "employee_role": {"type": ["string", "null"]},
                    "term_months": {"type": ["integer", "null"]},
                    "severance_months": {"type": ["integer", "null"]},
                    "severance_trigger": {"type": ["string", "null"]},
                    "equity_type": {"type": ["string", "null"]},
                    "vesting_period_months": {"type": ["integer", "null"]},
                    "vesting_cliff_months": {"type": ["integer", "null"]},
                    "acceleration_trigger": {"type": ["string", "null"]},
                    "raw_quote": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["clause_type", "raw_quote", "interpretation", "confidence"],
            },
        },
        "is_system": True,
    },
    {
        "slug": "spa_core",
        "title": "SPA Core Terms",
        "description": (
            "Extracts representations & warranties, indemnification caps, MAC/MAE clauses, "
            "closing conditions, purchase price mechanics, earnout provisions, basket/deductible "
            "structures, and survival periods from SPAs and acquisition agreements."
        ),
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
            "  - mac_carveouts: list of strings — specific MAC/MAE carveouts listed (e.g., pandemic, general economic conditions)\n"
            "  - adjustment_mechanism: string or null — purchase price adjustment method: 'locked_box', 'completion_accounts', or 'working_capital'\n"
            "  - adjustment_reference_date: string or null — reference date for locked box or working capital peg\n"
            "  - earnout_period_months: integer or null — earnout measurement period in months\n"
            "  - earnout_metric: string or null — metric triggering earnout (revenue, EBITDA, gross profit, etc.)\n"
            "  - earnout_cap: number or null — maximum earnout payment in USD\n"
            "  - closing_condition_party: string or null — 'buyer', 'seller', or 'mutual'\n"
            "  - raw_quote: verbatim clause text (max 400 chars)\n"
            "  - interpretation: plain-English one-sentence summary\n"
            "  - confidence: float 0-1 (how confident you are this is the relevant clause)\n\n"
            "Only include clauses you actually found. If no relevant clauses, return {\"clauses\": []}.\n\n"
            "Document excerpts:\n{candidate_chunks}"
        ),
        "output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "scope": {"type": ["string", "null"]},
                    "cap_amount": {"type": ["number", "null"]},
                    "cap_pct_ev": {"type": ["number", "null"]},
                    "basket_amount": {"type": ["number", "null"]},
                    "basket_type": {"type": ["string", "null"]},
                    "survival_months": {"type": ["integer", "null"]},
                    "mac_carveouts": {"type": "array", "items": {"type": "string"}},
                    "adjustment_mechanism": {"type": ["string", "null"]},
                    "adjustment_reference_date": {"type": ["string", "null"]},
                    "earnout_period_months": {"type": ["integer", "null"]},
                    "earnout_metric": {"type": ["string", "null"]},
                    "earnout_cap": {"type": ["number", "null"]},
                    "closing_condition_party": {"type": ["string", "null"]},
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
            existing.clause_types = pb_data.get("clause_types")
            existing.prompt_template = pb_data.get("prompt_template")
            existing.output_schema = pb_data.get("output_schema")
    db.commit()
    return created
