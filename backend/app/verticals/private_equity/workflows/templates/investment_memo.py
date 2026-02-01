"""Investment Memo workflow template definition.

Version: 2
Purpose: Provide a decision-ready investment memo with structured sections.

DUAL-PROMPT ARCHITECTURE:
- USER_PROMPT: Simple, editable template shown to users (deliverables.ai style)
- SYSTEM_PROMPT: Full technical implementation with formatting rules (hidden from users)
- Integration: USER_PROMPT is injected into SYSTEM_PROMPT's objective section

JSON Contract (summary):
Top-level keys — canonical output MUST include `sections` (array). Optional top-level objects provide STRUCTURED DATA.
NOTE: Financial data is EMBEDDED in the financial_performance section (NOT a separate top-level object).
{
  currency: "USD",  // REQUIRED - detect from document
  sections: [
    {
      key,
      title,
      content,
      citations?,
      confidence?,  // OPTIONAL float 0.0-1.0 (omit if uncertain, never null)
      highlights?,  // Visual metric cards
      key_metrics?,  // Quick scan pills
      financials?  // ONLY for financial_performance section - embedded structured data
    }
  ],
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
import json
from pathlib import Path

# User-facing prompt (shown in UI for editing)
INVESTMENT_MEMO_USER_PROMPT = """Generate an investment memo for {{company_name}} targeting {{target_audience}}. Analyze all aspects of the opportunity including business model, market position, financial performance, management team, risks, and growth opportunities. Provide structured insights with executive summary, detailed analysis sections, risk assessment, and actionable next steps. Support every quantitative claim with inline citations in document-token form (e.g. "[D1:p2]"). Include a complete reference list. Focus on delivering decision-ready insights for {{target_audience}} with clear recommendations. IMPORTANT: include a top-level "sections" array (each section with key, title, content). If you also produce top-level objects (financials, company_overview), those must match the corresponding sections.""".strip()

# Cacheable system prompt (100% static - no variables)
# This gets cached by Anthropic and reused across ALL workflow runs
INVESTMENT_MEMO_SYSTEM_PROMPT_CACHEABLE = """
Generate an ULTRA-CONCISE, professional-grade investment memo for Private Equity decision-making.

⚠️⚠️⚠️ EXTREME BREVITY REQUIRED ⚠️⚠️⚠️
TARGET: Each section = 100-150 words MAX (2-3 SHORT paragraphs)
TOTAL MEMO: Should be readable in 5-7 minutes

RULES FOR BREVITY:
- NO more than 2-3 paragraphs per section
- Each paragraph: 2-3 sentences MAX
- Bullet lists: 3-5 items ONLY (not 7!)
- Use ONLY the most critical insights - omit nice-to-have details
- Think: "Elevator pitch for each section"
- If you can say it in fewer words, DO IT

# ============================================================================
# OUTPUT FORMAT
# ============================================================================
Your response will be automatically parsed as structured JSON.
You do NOT need to worry about JSON syntax — focus on content quality.
The system enforces the structure. Your job: generate the RIGHT content.

# ============================================================================
# SECTIONS — You MUST generate ALL 13
# ============================================================================
⚠️ CRITICAL: Generate ALL 13 sections below. Do NOT stop early.
The system cannot recover missing sections.

REQUIRED (12):
1)  executive_overview      → "Executive Overview"
2)  company_overview        → "Company Overview"
3)  market_competition      → "Market Competition"
4)  financial_performance   → "Financial Performance"
5)  track_record_value_creation → "Track Record & Value Creation"
6)  risks                   → "Risks"
7)  opportunities           → "Opportunities"
8)  management_culture      → "Management & Culture"
9)  esg_snapshot            → "ESG Snapshot"
10) valuation_scenarios     → "Valuation Scenarios"
11) next_steps              → "Next Steps"
12) inconsistencies         → "Inconsistencies"

OPTIONAL (1):
13) unit_economics          → "Unit Economics" (only if data exists)

# ============================================================================
# CITATIONS — MUST use [D1:p2] format
# ============================================================================
⚠️ This is NOT enforced automatically. You MUST get this right.

CORRECT format: [D1:p2] means Document 1, page 2
- D = Document number (matches the source documents provided)
- p = Page number within that document

Examples:
✅ "Revenue was $21.4M [D1:p5]"
✅ "citations": ["[D1:p2]", "[D3:p5]"]
❌ "Revenue was $21.4M [1]"          ← Wrong! Not numeric
❌ "Revenue was $21.4M [Source 1]"   ← Wrong! Not the format
❌ "citations": "[D1:p2]"            ← Wrong! Must be array

Rules:
- Every quantitative claim needs a citation
- citations array = all unique citations used in that section
- top-level "references" = all unique citations across entire memo

# ============================================================================
# ENUM VALUES — Must be exact (case-sensitive)
# ============================================================================
⚠️ These are NOT enforced automatically. Use EXACTLY these values:

Risk severity (one of):
  "High" | "Medium" | "Low"

Opportunity impact (one of):
  "High" | "Medium" | "Low"

ESG factor status (one of):
  "Positive" | "Neutral" | "Negative"

Examples:
✅ {"severity": "High"}
✅ {"impact": "Medium"}
✅ {"status": "Positive"}
❌ {"severity": "high"}       ← Wrong! Must be capitalized
❌ {"impact": "Critical"}     ← Wrong! Not a valid value
❌ {"status": "Good"}         ← Wrong! Must be Positive/Neutral/Negative

# ============================================================================
# SECTION CONTENT STRUCTURE
# ============================================================================

1. highlights (3-5 items) — Key data points rendered as visual cards
   Example:
   "highlights": [
     {"label": "2023 Revenue", "value": "$111.9M", "citation": "[D1:p5}"},
     {"label": "EBITDA Margin", "value": "40.5%", "citation": "[D1:p5]"},
     {"label": "Locations", "value": "1,200+", "citation": "[D1:p2]"}
   ]

2. key_metrics (3-6 items) — Supporting metrics rendered as pills
   Example:
   "key_metrics": [
     {"label": "Revenue CAGR", "value": "25%", "citation": "[D1:p5]"},
     {"label": "Debt/EBITDA", "value": "4.5x", "citation": "[D1:p5]"}
   ]

3. content — Markdown narrative (100-150 words MAX)
   Use: ### headers, **bold**, bullet lists, inline citations
   Example:
   "### Revenue Growth\\n\\nRevenue grew from $85.2M to $111.9M over 3 years [D1:p5].
   This reflects consistent same-store sales growth.\\n\\n### Key Risk\\n\\n
   Leverage at 4.5x Debt/EBITDA remains elevated [D1:p5]."

4. citations — Array of all citations used in this section
   "citations": ["[D1:p2]", "[D1:p5]"]

# ============================================================================
# FINANCIAL PERFORMANCE — Special Structure
# ============================================================================
⚠️ This section has an embedded "financials" object. Others don't.

The financials block must have:
- currency: MUST match the top-level currency exactly
- historical: Array of yearly data

⚠️ Revenue values in historical must be plain number strings:
✅ "revenue": "111900000"
✅ "revenue": "85200000"
❌ "revenue": "$111.9M"      ← Wrong in historical (use formatted in content)
❌ "revenue": 111900000      ← Keep as string

Example:
"financials": {
  "currency": "USD",
  "historical": [
    {"year": 2021, "revenue": "85200000", "citation": "[D1:p5]"},
    {"year": 2022, "revenue": "98700000", "citation": "[D1:p5]"},
    {"year": 2023, "revenue": "111900000", "citation": "[D1:p5]"}
  ]
}

Include ALL available years. Use formatted values ($85.2M) in the content narrative.

# ============================================================================
# NEXT STEPS — Required Fields
# ============================================================================
⚠️ Each next_step MUST have all 4 fields:

"next_steps": [
  {
    "priority": 1,              ← integer, 1 = highest
    "action": "Review financials",  ← what to do
    "owner": "Analyst",         ← who owns it
    "timeline_days": 14         ← integer, days to complete
  }
]

# ============================================================================
# CURRENCY — Must be consistent
# ============================================================================
- Detect currency from the documents ($=USD, €=EUR, £=GBP)
- Set top-level "currency" field
- If financial_performance has a financials block, its currency MUST match

# ============================================================================
# META
# ============================================================================
Always include:
"meta": {"version": 2}

version must be the integer 2 (not "2", not 2.0).

# ============================================================================
# CONTENT FORMATTING
# ============================================================================
✅ Use ### headers, **bold**, bullets, numbers with units ($M, %, x)
✅ Inline citations after quantitative claims: [D1:p2]
✅ 100-150 words per section content
❌ Don't exceed 3-5 bullet items
❌ Don't write long paragraphs (2-3 sentences max)
❌ Don't use null for missing fields — omit them instead

# ============================================================================
⚠️ WRITING GUIDELINES FOR SECTION CONTENT:
- HARD LIMIT: 100-150 words per section "content" field
- Structure: 2-3 SHORT paragraphs (2-3 sentences each)
- Bullet lists: 3-5 items MAX (choose the TOP items only)
- Use ### headers sparingly - only when absolutely needed
- Every word must earn its place - CUT ruthlessly
- Think: "What are the 3 most important facts for this section?"
- Focus on DECISION-READY insights for Private Equity investors

# ============================================================================
# SECTION-SPECIFIC FORMATS — Special Instructions
# ============================================================================

## Financial Performance Section (CRITICAL - Different Structure):
The "financial_performance" section has EMBEDDED "financials" object (NOT top-level).
{
  "key": "financial_performance",
  "highlights": [...],  // Visual metrics
  "key_metrics": [...],  // Quick pills
  "financials": {  // EMBEDDED structured data for tables
    "currency": "USD",  // MUST match top-level currency
    "fiscal_year_end": "December 31",
    "historical": [
      {"year": 2023, "revenue": 111900000, "ebitda": 45300000, "margin": 0.405, "citation": "[D1:p5]"}
    ],
    "metrics": {"rev_cagr": 0.25, "ebitda_margin_latest": 0.405, "citation": ["[D1:p5]"]}
  },
  "content": "### Revenue Growth\n\n- 2023: $111.9M (+13.4%) [D1:p5]..."
}
CRITICAL: Include ALL available years (2008-2023 if found), raw numbers in historical, formatted in content.

## Currency Detection (CRITICAL — Sets Top-Level Field):
- Look for: $, €, £, ¥ symbols OR USD, EUR, GBP codes in financials
- Set top-level "currency" AND section.financials.currency to SAME value
- If unclear: "UNKNOWN" and add to inconsistencies

# ============================================================================
# ⚠️⚠️⚠️ CRITICAL REMINDER: GENERATE ALL 13 SECTIONS ⚠️⚠️⚠️
# ============================================================================

Your "sections" array in the JSON output MUST contain all 13 section objects:
[
  {"key": "executive_overview", "title": "Executive Overview", ...},
  {"key": "company_overview", "title": "Company Overview", ...},
  {"key": "market_competition", "title": "Market Competition", ...},
  {"key": "financial_performance", "title": "Financial Performance", ...},
  {"key": "track_record_value_creation", "title": "Track Record & Value Creation", ...},
  {"key": "risks", "title": "Risks", ...},
  {"key": "opportunities", "title": "Opportunities", ...},
  {"key": "management_culture", "title": "Management & Culture", ...},
  {"key": "esg_snapshot", "title": "ESG Snapshot", ...},
  {"key": "valuation_scenarios", "title": "Valuation Scenarios", ...},
  {"key": "next_steps", "title": "Next Steps", ...},
  {"key": "inconsistencies", "title": "Inconsistencies", ...},

  {"key": "unit_economics", "title": "Unit Economics", ...} (optional),
]

⚠️⚠️⚠️ FINAL WARNING: If you stop after generating only a few sections, the output will be REJECTED.
Generate the COMPLETE investment memo with ALL 13 sections. This is MANDATORY.
""".strip()

# Prompt function for caching-optimized architecture
def get_investment_memo_prompt(variables: dict, custom_prompt: str = None) -> dict:
    """Generate separate system prompt (cacheable) and user message (dynamic).

    Args:
        variables: Template variables (company_name, target_audience, etc.)
        custom_prompt: User's edited version of the prompt (if provided)

    Returns:
        Dict with:
            - system_prompt: Static instructions (100% cacheable across all runs)
            - user_message: Dynamic variables + custom objective + context
    """
    # Static system prompt (cached by Anthropic)
    system_prompt = INVESTMENT_MEMO_SYSTEM_PROMPT_CACHEABLE

    # Build dynamic user message with all variables
    company_name = variables.get('company_name', '[Company Name]')
    target_audience = variables.get('target_audience', 'IC')
    include_financials = variables.get('include_financials', True)
    focus_risks = variables.get('focus_risks', False)
    include_esg = variables.get('include_esg', True)
    include_management_culture = variables.get('include_management_culture', True)
    include_valuation = variables.get('include_valuation', True)
    include_scenarios = variables.get('include_scenarios', True)

    # Build configuration text
    config_parts = []
    config_parts.append(f"Company: {company_name}")
    config_parts.append(f"Target Audience: {target_audience}")
    config_parts.append(f"Include Financials: {include_financials}")
    config_parts.append(f"Focus on Risks: {focus_risks}")
    config_parts.append(f"Include ESG: {include_esg}")
    config_parts.append(f"Include Management & Culture: {include_management_culture}")
    config_parts.append(f"Include Valuation: {include_valuation}")
    config_parts.append(f"Include Scenarios: {include_scenarios}")

    configuration = "\n".join(config_parts)

    # Build user message
    user_message_parts = [
        f"ANALYSIS REQUEST:",
        f"{configuration}",
    ]

    # Add custom objective if provided
    if custom_prompt:
        user_message_parts.append(f"\nUSER OBJECTIVE:")
        user_message_parts.append(custom_prompt)
        user_message_parts.append("\nFollow this objective while adhering to all formatting and structure requirements.")

    user_message_parts.append("\nDOCUMENT CONTEXT:")
    user_message_parts.append("{{CONTEXT}}")  # Placeholder - will be replaced by caller
    user_message_parts.append("\n" + "="*80)
    user_message_parts.append("⚠️⚠️⚠️ CRITICAL INSTRUCTION - READ CAREFULLY ⚠️⚠️⚠️")
    user_message_parts.append("="*80)
    user_message_parts.append("\nYou MUST generate ALL 13 sections in your JSON response:")
    user_message_parts.append("1. executive_overview")
    user_message_parts.append("2. company_overview")
    user_message_parts.append("3. market_competition")
    user_message_parts.append("4. financial_performance")
    user_message_parts.append("5. unit_economics (optional)")
    user_message_parts.append("6. track_record_value_creation")
    user_message_parts.append("7. risks")
    user_message_parts.append("8. opportunities")
    user_message_parts.append("9. management_culture")
    user_message_parts.append("10. esg_snapshot")
    user_message_parts.append("11. valuation_scenarios")
    user_message_parts.append("12. next_steps")
    user_message_parts.append("13. inconsistencies")
    user_message_parts.append("\nDO NOT STOP after generating only executive_overview, company_overview, or market_competition.")
    user_message_parts.append("CONTINUE until you have generated ALL 13 sections.")
    user_message_parts.append("\nGenerate the COMPLETE investment memo. This is MANDATORY.")
    user_message_parts.append("="*80)

    user_message = "\n".join(user_message_parts)

    return {
        "system_prompt": system_prompt,
        "user_message": user_message
    }

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
        "max_chunks": 10
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
        "max_chunks": 10
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
        "max_chunks": 10
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
        "max_chunks": 20
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
        "max_chunks": 10
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
        "max_chunks": 10
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
        "max_chunks": 15
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
        "max_chunks": 10
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
        "max_chunks": 10
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
        "max_chunks": 10
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

# Load output schema from JSON file
_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "investment_memo.schema.json"

with open(_SCHEMA_PATH, "r") as f:
    INVESTMENT_MEMO_OUTPUT_SCHEMA = json.load(f)

TEMPLATE = {
    "name": "Investment Memo",
    "domain": "private_equity",
    "category": "deal_flow",
    "description": "Decision-ready investment memo with structured thesis, risks, opportunities & scenarios",
    "prompt_template": INVESTMENT_MEMO_SYSTEM_PROMPT_CACHEABLE,  # Static system prompt (cacheable)
    "user_prompt_template": INVESTMENT_MEMO_USER_PROMPT,  # User-friendly version for editing
    "prompt_generator": get_investment_memo_prompt,  # Function to combine user + system prompts
    "retrieval_spec": INVESTMENT_MEMO_RETRIEVAL_SPEC,  # Workflow-specific retrieval sections
    "variables_schema": INVESTMENT_MEMO_SCHEMA,
    "output_schema": INVESTMENT_MEMO_OUTPUT_SCHEMA,
    "output_format": "json",
    "min_documents": 1,
    "max_documents": 5,
    "version": 2,
    "user_prompt_max_length": 1000,  # Limit user edits to 1000 characters
}
