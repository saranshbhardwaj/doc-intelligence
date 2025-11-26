"""Investment Memo workflow template definition.

Version: 2
Purpose: Provide a decision-ready investment memo with structured sections.

DUAL-PROMPT ARCHITECTURE:
- USER_PROMPT: Simple, editable template shown to users (deliverables.ai style)
- SYSTEM_PROMPT: Full technical implementation with formatting rules (hidden from users)
- Integration: USER_PROMPT is injected into SYSTEM_PROMPT's objective section

JSON Contract (summary):
Top-level keys — canonical output MUST include `sections` (array). Optional top-level objects (financials, company_overview, etc.) are allowed only as MIRRORS of the corresponding `sections` entries.
{
  sections: [ { key, title, content, citations?, confidence? } ],
  financials?: { historical: [ { year, revenue?, ebitda?, margin?, citation } ], metrics?: { rev_cagr?, ebitda_margin_latest?, citation[] } },
  valuation?: { base_case, upside_case, downside_case },
  risks: [ { description, category, severity, citations[] } ],
  opportunities: [ { description, category, impact, citations[] } ],
  management?: { summary, strengths[], gaps[], citations[] },
  esg?: { factors: [ { dimension, status, citation? } ], overall },
  next_steps: [ { priority, action, owner, timeline_days? } ],
  inconsistencies: [ str ],
  references: [ citationToken ],
  meta: { version: 2 }
}

Edge Cases:
- Missing optional sections: simply omitted, not empty objects.
- Empty risks/opportunities arrays allowed (still include keys).
- Citations in references must be unique union of all citation arrays.
- If financials.historical missing revenue/ebitda for a year, omit those fields rather than blank strings.
- Valuation omitted unless include_valuation AND include_scenarios true.
"""

# User-facing prompt (shown in UI for editing)
INVESTMENT_MEMO_USER_PROMPT = """Generate a comprehensive investment memo for {{company_name}} targeting {{target_audience}}. Analyze all aspects of the opportunity including business model, market position, financial performance, management team, risks, and growth opportunities. Provide structured insights with executive summary, detailed analysis sections, risk assessment, and actionable next steps. Support every quantitative claim with inline citations in document-token form (e.g. "[D1:p2]"). Include a complete reference list. Focus on delivering decision-ready insights for {{target_audience}} with clear recommendations. IMPORTANT: include a top-level "sections" array (each section with key, title, content). If you also produce top-level objects (financials, company_overview), those must match the corresponding sections.""".strip()

# Full system prompt (technical implementation - not shown to users)
INVESTMENT_MEMO_SYSTEM_PROMPT = """
Generate a professional-grade investment memo for {{company_name}} targeting {{target_audience}}.

{% if custom_objective is defined and custom_objective %}
USER OBJECTIVE:
{{ custom_objective }}

Follow this objective while adhering to all formatting and structure requirements below.
{% endif %}

OUTPUT STYLE — CRITICAL (READ CAREFULLY)
1) MUST produce a top-level key named "sections" containing an array of section objects. This is the canonical output format and the schema validator will enforce it.
   - "sections" is authoritative; top-level objects (company_overview, financials, risks, valuation, etc.) are OPTIONAL MIRRORS only.
   - If a top-level object is present it MUST accurately mirror the corresponding section (same substance).
   - "sections" must contain at least 2 items and each section must include "key", "title", and "content".
2) Citation format MUST be document-token form (example: "[D1:p2]"). Do NOT use numeric-only citations like "[1]".
3) Return STRICT JSON only. No explanatory text, no code fences, no extra keys outside the contract.
4) If a field is unknown or not available, OMIT it rather than set it to null. Exceptions: "risks" and "opportunities" must always be present (they may be empty arrays).
5) The LLM MUST output a top-level "currency" field (3-letter ISO code, e.g. "USD"). If you detect a primary currency, set that code at top-level and in financials.currency. If currency is ambiguous, set "currency": "UNKNOWN" and include that ambiguity in "inconsistencies".

CRITICAL FORMATTING RULES:
1. Section content MUST be well-formatted Markdown with proper structure
2. Use headings (###), bold (**text**), bullet points, and numbered lists
3. Numbers MUST include units (M for millions, B for billions, K for thousands)
4. Percentages MUST include the % symbol
5. Every **quantitative** factual claim MUST have an inline citation in document-token form (e.g., "[D1:p2]"). For qualitative claims include a citation where the claim is explicitly sourced.
6. Content should be human-readable and professional

Objective:
Synthesise a decision-ready view combining strategic, market, financial, operational, management, ESG and valuation insights. Provide structured JSON for downstream rendering & validation.

Dynamic inclusion (guided by variables):
- Include financial & growth tables if {{include_financials}} is true.
- Include extended risks/opportunities if {{focus_risks}} is true.
- Include ESG snapshot if {{include_esg}} is true.
- Include management & culture section if {{include_management_culture}} is true.
- Include valuation scenarios if {{include_valuation}} is true.
- Include scenario analysis (base/upside/downside) if {{include_scenarios}} is true.

Section object structure (REQUIRED format):
"sections": [
  {
    "key": "executive_overview",
    "title": "Executive Overview",
    "content": "### Investment Highlights\\n\\n**Company:** NPC International is the largest Pizza Hut franchisee globally, operating 1,200+ locations across the US [D1:p2].\\n\\n**Financial Performance:** 2023 revenue reached $111.9M with EBITDA of $45.3M (40.5% margin) [D3:p2]. The company demonstrated strong growth with 3-year revenue CAGR of 25% [D3:p2].\\n\\n**Market Position:**\\n- #1 market share in the QSR pizza segment [D3:p2]\\n- Strong unit economics with average unit volume of $1.2M [D3:p2]\\n- Defensive business model with recurring revenue streams\\n\\n**Key Risks:**\\n- Customer concentration: Top 3 customers represent 45% of revenue [D3:p2]\\n- High leverage at 4.5x Net Debt/EBITDA [D3:p2]\\n\\n**Investment Thesis:** The company presents a compelling opportunity due to its market leadership, proven track record, and clear path to operational improvements.",
    "citations": ["[D1:p2]", "[D3:p2]"],
    "confidence": "High"
  },
  {
    "key": "company_overview",
    "title": "Company Overview",
    "content": "### Business Description\\n\\n**Company Name:** NPC International LLC [D1:p2]\\n**Industry:** Restaurant Franchising - Food Service\\n**Headquarters:** United States\\n\\n### Business Model\\n\\nNPC operates as a franchisee of Pizza Hut, generating revenue through:\\n- Dine-in services (40%)\\n- Delivery operations (35%)\\n- Takeout orders (25%)\\n\\nThe company benefits from the Pizza Hut brand while maintaining operational control over its locations [D1:p2].\\n\\n### Key Differentiators\\n\\n- **Scale:** Largest franchisee in the Pizza Hut system\\n- **Geographic Reach:** Presence in 28 states with dense market coverage\\n- **Operational Excellence:** Industry-leading same-store sales growth of 8.2% [D2:p5]",
    "citations": ["[D1:p2]", "[D2:p5]"]
  }
]

CONTENT FORMATTING EXAMPLES:

✅ GOOD - Well-formatted with structure:
"content": "### Financial Highlights\\n\\n**Revenue Growth:**\\n- 2021: $85.2M\\n- 2022: $98.7M (+15.8%)\\n- 2023: $111.9M (+13.4%)\\n\\n**Profitability Metrics:**\\n- EBITDA Margin: 40.5% (best-in-class) [D1:p2]\\n- Net Income Margin: 12.3%\\n- ROE: 18.5%\\n\\nThe company has demonstrated consistent margin expansion over the past 3 years, driven by operational improvements and economies of scale [D1:p2]."

❌ BAD - No structure or formatting:
"content": "Revenue was 111900000 in 2023. ebitda was 45300000. margin was 0.405"

REQUIRED SECTIONS (in order):
1. executive_overview (≤200 words, high-level summary)
2. company_overview
3. market_competition
4. financial_performance (conditional on {{include_financials}})
5. unit_economics (optional)
6. track_record_value_creation
7. risks
8. opportunities
9. management_culture (conditional on {{include_management_culture}})
10. esg_snapshot (conditional on {{include_esg}})
11. valuation_scenarios (conditional on {{include_valuation}} AND {{include_scenarios}})
12. next_steps
13. inconsistencies

CITATION RULES:
- Use inline citations [D1:p2], [D2:p3], [D3:p5] within content
- Map citations to document references in the citations array
- Format: "[D1:p2]" where D1 = Document 1, p2 = Page 2
- Every quantitative claim REQUIRES a citation

FINANCIAL DATA FORMATTING:
- Revenue: Use M/B suffixes (e.g., "$111.9M", "$1.2B")
- Margins: Include % (e.g., "40.5%", "15.2%")
- Multiples: Include x (e.g., "9.5x EBITDA", "1.8x Revenue")
- Growth rates: Include % (e.g., "25% CAGR")

Financial performance object structure:
"financials": {
  "currency": "<MUST SET - 3-letter ISO code>",  // LLM MUST set this (e.g., "USD", "EUR"); if unclear set "UNKNOWN"
  "fiscal_year_end": "December 31",  // If mentioned in document
  "historical": [
    {
      "year": 2023,
      "revenue": 111900000,  // raw number (base units); section content should show formatted "$111.9M"
      "ebitda": 45300000,
      "margin": 0.405,       // Decimal (0.405 = 40.5%)
      "citation": "[D1:p5]"
    }
  ],
  "metrics": {
    "rev_cagr": 0.25,              // Decimal (0.25 = 25%)
    "ebitda_margin_latest": 0.405,
    "citation": ["[D1:p6]"]
  }
}

CURRENCY DETECTION (CRITICAL):
- Look for currency symbols: $, €, £, ¥, etc.
- Look for currency codes: USD, EUR, GBP, JPY, CNY, etc.
- Check financial statement headers, footnotes, and amounts
- Set "currency" field based on what you find
- If multiple currencies, use the primary operating currency
- Default to "USD" ONLY if truly unclear

IMPORTANT: Store raw numbers (111900000) in financials, but format them nicely ($111.9M) in section content.

Risk item schema:
{
  "description": "Customer concentration: Top 3 clients represent 45% of revenue, creating dependency risk",
  "category": "Commercial",
  "severity": "High",
  "citations": ["[D1:p12]"]
}

Opportunity item schema:
{
  "description": "Geographic expansion into underserved markets could add $50M-75M in annual revenue",
  "category": "Growth",
  "impact": "High",
  "citations": ["[D2:p8]"]
}

Valuation scenarios (conditional):
"valuation": {
  "base_case": {
    "ev": 500000000,           // Raw number
    "multiple": 9.5,
    "irr": 0.22,               // Decimal (0.22 = 22%)
    "assumptions": "Assumes revenue growth of 15% annually, EBITDA margin expansion to 42%, exit at 10x EBITDA in year 5",
    "citations": ["[D3:p15]"]
  },
  "upside_case": { ... },
  "downside_case": { ... }
}

Management & culture:
"management": {
  "summary": "Strong, experienced management team with average tenure of 12 years. CEO has successfully scaled two previous portfolio companies.",
  "strengths": [
    "Deep industry expertise and relationships",
    "Proven track record of value creation",
    "Strong alignment through equity ownership (15% fully diluted)"
  ],
  "gaps": [
    "Limited digital/e-commerce experience",
    "No dedicated CFO (currently interim)"
  ],
  "citations": ["[D2:p20]", "[D2:p21]"]
}

ESG snapshot:
"esg": {
  "factors": [
    {
      "dimension": "environment",
      "status": "Positive",
      "citation": "[D3:p5]"
    },
    {
      "dimension": "social",
      "status": "Neutral",
      "citation": "[D3:p6]"
    }
  ],
  "overall": "ESG risks are manageable with no material red flags. The company has implemented sustainability initiatives reducing carbon footprint by 20% over 3 years."
}

Next steps:
"next_steps": [
  {
    "priority": 1,
    "action": "Complete management interviews and reference checks",
    "owner": "Investor",
    "timeline_days": 14
  },
  {
    "priority": 2,
    "action": "Conduct detailed financial quality of earnings review",
    "owner": "Joint",
    "timeline_days": 21
  }
]

Return STRICT JSON with top-level keys:
{
  "currency": "USD",  // DETECT FROM DOCUMENT - Set this FIRST based on currency found in financials
  "sections": [...],
  "company_overview": {
    "company_name": str,
    "company_id": str,
    "industry": str,
    "headquarters": str,
    "description": str,
    "provenance": { "section": str, "page": int, "excerpt": str },
    "confidence": 0.0-1.0
  },
  "financials": {
    "currency": "USD",  // MUST MATCH top-level currency
    ...
  },
  "valuation": {...},
  "risks": [...],
  "opportunities": [...],
  "management": {...},
  "esg": {...},
  "next_steps": [...],
  "inconsistencies": [...],
  "references": ["[D1:p2]", "[D1:p3]"],
  "meta": { "version": 2 }
}

CRITICAL OUTPUT RULES:
1. Section content MUST be well-formatted Markdown
2. Use proper headings, bullets, bold, and spacing
3. Include units on all numbers ($M, B, K, %, x)
4. Cite every factual claim
5. Make content human-readable and professional
6. Omit optional sections if data not available (do NOT include empty objects)
7. Always include meta.version and currency
8. meta.version MUST be the integer 2 (exactly `2`). Do NOT emit 2.0 or "2".

NO markdown code blocks in output - return pure JSON only.
""".strip()

# Combined prompt function
def get_investment_memo_prompt(variables: dict, custom_prompt: str = None) -> str:
    """Generate the final prompt by combining user prompt with system prompt.

    Args:
        variables: Template variables (company_name, target_audience, etc.)
        custom_prompt: User's edited version of the prompt (if provided)

    Returns:
        Final prompt with all variables filled in
    """
    from jinja2 import Template

    # Use custom_prompt if provided, otherwise use default user prompt
    objective = custom_prompt if custom_prompt else INVESTMENT_MEMO_USER_PROMPT

    # Add custom_objective to variables
    variables_with_objective = dict(variables)
    variables_with_objective['custom_objective'] = objective if custom_prompt else ""

    # Render the system prompt with all variables
    template = Template(INVESTMENT_MEMO_SYSTEM_PROMPT)
    return template.render(**variables_with_objective)

# Retrieval specification for Investment Memo workflow
# Defines what content to retrieve for each section
INVESTMENT_MEMO_RETRIEVAL_SPEC = [
    {
        "key": "executive_overview",
        "title": "EXECUTIVE OVERVIEW",
        "queries": [
            "investment highlights",
            "key strengths",
            "business overview",
            "executive summary",
            "investment thesis"
        ],
        "prefer_tables": False,
        "priority": "critical",
        "max_chunks": 15
    },
    {
        "key": "company_overview",
        "title": "COMPANY OVERVIEW",
        "queries": [
            "company description",
            "business model",
            "products and services",
            "corporate structure",
            "company history"
        ],
        "prefer_tables": False,
        "priority": "high",
        "max_chunks": 20
    },
    {
        "key": "market_competition",
        "title": "MARKET & COMPETITIVE LANDSCAPE",
        "queries": [
            "market size",
            "market share",
            "competitive position",
            "competitors",
            "industry trends",
            "competitive advantages"
        ],
        "prefer_tables": False,
        "priority": "medium",
        "max_chunks": 15
    },
    {
        "key": "financial_performance",
        "title": "FINANCIAL PERFORMANCE",
        "queries": [
            "revenue growth",
            "ebitda margin",
            "profitability",
            "financial statements",
            "income statement",
            "revenue breakdown",
            "financial metrics"
        ],
        "prefer_tables": True,  # Critical: financial tables!
        "priority": "critical",
        "max_chunks": 25
    },
    {
        "key": "unit_economics",
        "title": "UNIT ECONOMICS",
        "queries": [
            "unit economics",
            "customer acquisition cost",
            "lifetime value",
            "churn rate",
            "average revenue per user"
        ],
        "prefer_tables": True,
        "priority": "medium",
        "max_chunks": 12
    },
    {
        "key": "track_record",
        "title": "TRACK RECORD & VALUE CREATION",
        "queries": [
            "historical performance",
            "growth trajectory",
            "value creation",
            "past acquisitions",
            "operational improvements"
        ],
        "prefer_tables": False,
        "priority": "medium",
        "max_chunks": 15
    },
    {
        "key": "risks",
        "title": "RISK FACTORS",
        "queries": [
            "risk factors",
            "customer concentration",
            "regulatory risk",
            "operational challenges",
            "market risks",
            "key risks"
        ],
        "prefer_tables": False,
        "priority": "high",
        "max_chunks": 20
    },
    {
        "key": "opportunities",
        "title": "GROWTH OPPORTUNITIES",
        "queries": [
            "growth opportunities",
            "expansion plans",
            "market opportunities",
            "strategic initiatives",
            "new products",
            "geographic expansion"
        ],
        "prefer_tables": False,
        "priority": "high",
        "max_chunks": 15
    },
    {
        "key": "management_culture",
        "title": "MANAGEMENT & ORGANIZATIONAL CULTURE",
        "queries": [
            "management team",
            "executive leadership",
            "organizational culture",
            "board of directors",
            "key personnel",
            "leadership experience"
        ],
        "prefer_tables": False,
        "priority": "medium",
        "max_chunks": 15
    },
    {
        "key": "esg",
        "title": "ESG FACTORS",
        "queries": [
            "environmental impact",
            "social responsibility",
            "corporate governance",
            "sustainability",
            "ESG factors",
            "carbon footprint"
        ],
        "prefer_tables": False,
        "priority": "low",
        "max_chunks": 10
    },
    {
        "key": "valuation",
        "title": "VALUATION & SCENARIOS",
        "queries": [
            "valuation",
            "enterprise value",
            "valuation multiples",
            "comparable companies",
            "DCF analysis",
            "pricing"
        ],
        "prefer_tables": True,
        "priority": "medium",
        "max_chunks": 15
    },
    {
        "key": "next_steps",
        "title": "RECOMMENDED NEXT STEPS",
        "queries": [
            "recommended actions",
            "next steps",
            "follow-up diligence",
            "action items",
            "due diligence recommendations"
        ],
        "prefer_tables": False,
        "priority": "high",
        "max_chunks": 10
    }
]

INVESTMENT_MEMO_SCHEMA = {
    "variables": [
        {"name": "company_name", "type": "string", "required": True, "description": "Company name being analyzed"},
        {"name": "target_audience", "type": "enum", "choices": ["IC", "Partners", "Board"], "required": True, "description": "Primary audience for the memo"},
        {"name": "include_financials", "type": "boolean", "default": True},
        {"name": "focus_risks", "type": "boolean", "default": False},
        {"name": "years_back", "type": "integer", "default": 3, "min": 1, "max": 10},
        {"name": "include_esg", "type": "boolean", "default": True},
        {"name": "include_management_culture", "type": "boolean", "default": True},
        {"name": "include_valuation", "type": "boolean", "default": True},
        {"name": "include_scenarios", "type": "boolean", "default": True},
        {"name": "scenario_years", "type": "integer", "default": 5, "min": 2, "max": 10},
        {"name": "max_risks", "type": "integer", "default": 8, "min": 1, "max": 20},
        {"name": "max_opportunities", "type": "integer", "default": 6, "min": 1, "max": 15},
        {"name": "return_confidence", "type": "boolean", "default": True},
        {"name": "tone", "type": "enum", "choices": ["neutral", "concise", "detailed"], "default": "neutral"},
        {"name": "format_level", "type": "enum", "choices": ["summary", "expanded"], "default": "expanded"},
    ]
}

TEMPLATE = {
    "name": "Investment Memo",
    "category": "deal_flow",
    "description": "Decision-ready investment memo with structured thesis, risks, opportunities & scenarios",
    "prompt_template": INVESTMENT_MEMO_SYSTEM_PROMPT,  # Full technical prompt
    "user_prompt_template": INVESTMENT_MEMO_USER_PROMPT,  # User-friendly version for editing
    "prompt_generator": get_investment_memo_prompt,  # Function to combine user + system prompts
    "retrieval_spec": INVESTMENT_MEMO_RETRIEVAL_SPEC,  # Workflow-specific retrieval sections
    "variables_schema": INVESTMENT_MEMO_SCHEMA,
    "output_format": "json",
    "min_documents": 1,
    "max_documents": 5,
    "version": 2,
    "user_prompt_max_length": 1000,  # Limit user edits to 1000 characters
}
