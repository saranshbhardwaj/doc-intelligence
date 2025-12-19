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
# CRITICAL OUTPUT RULES — MANDATORY
# ============================================================================
⚠️ CRITICAL: Your ENTIRE response must be ONLY valid JSON. Start IMMEDIATELY with the opening brace {
   DO NOT write ANY text before the JSON. NO preamble. NO explanations. ONLY JSON.

1. First character of response: { (opening brace)
2. Last character of response: } (closing brace)
3. ⚠️⚠️⚠️ CRITICAL: Generate ALL 13 required sections listed below - do NOT stop early ⚠️⚠️⚠️
   REQUIRED SECTIONS (you MUST generate all 13):
   1) executive_overview
   2) company_overview
   3) market_competition
   4) financial_performance
   5) unit_economics (optional)
   6) track_record_value_creation
   7) risks
   8) opportunities
   9) management_culture
   10) esg_snapshot
   11) valuation_scenarios
   12) next_steps
   13) inconsistencies
4. MUST include top-level "currency" field (detect from document: "USD", "EUR", etc.)
5. ALL citations MUST use document-token format: [D1:p2] (NOT numeric [1])
6. ⚠️ CRITICAL: "citations" field MUST be a JSON array: ["[D1:p1]", "[D1:p3]"] NOT "[D1:p1]", "[D1:p3]"
7. OMIT unknown fields (don't use null) — EXCEPT: "risks" and "opportunities" arrays always required

# ============================================================================
# JSON CONTRACT — Canonical Schema
# ============================================================================

⚠️ WRITING GUIDELINES FOR SECTION CONTENT:
- HARD LIMIT: 100-150 words per section "content" field
- Structure: 2-3 SHORT paragraphs (2-3 sentences each)
- Bullet lists: 3-5 items MAX (choose the TOP items only)
- Use ### headers sparingly - only when absolutely needed
- Every word must earn its place - CUT ruthlessly
- Think: "What are the 3 most important facts for this section?"

Section object structure (ENHANCED format with structured highlights):
"sections": [
  {
    "key": "executive_overview",
    "title": "Executive Overview",

    // Structured highlights for key stats (renders as elegant cards/pills)
    "highlights": [
      {
        "type": "company",
        "label": "Company",
        "value": "World's largest Pizza Hut franchisee",
        "detail": "1,200+ locations across the US",
        "citation": "[D1:p2]"
      },
      {
        "type": "metric",
        "label": "2023 Revenue",
        "value": 111900000,
        "formatted": "$111.9M",
        "trend": "up",
        "trend_value": "25%",
        "citation": "[D3:p2]"
      },
      {
        "type": "metric",
        "label": "EBITDA",
        "value": 45300000,
        "formatted": "$45.3M",
        "detail": "40.5% margin",
        "citation": "[D3:p2]"
      },
      {
        "type": "stat",
        "label": "Market Position",
        "value": "#1 in QSR pizza segment",
        "citation": "[D3:p2]"
      }
    ],

    // Key metrics for quick scanning (renders as metric pills)
    "key_metrics": [
      { "label": "Revenue CAGR", "value": "25%", "period": "3-year", "citation": "[D3:p2]" },
      { "label": "EBITDA Margin", "value": "40.5%", "status": "strong", "citation": "[D3:p2]" },
      { "label": "Locations", "value": "1,200+", "citation": "[D1:p2]" },
      { "label": "Debt/EBITDA", "value": "4.5x", "status": "monitor", "citation": "[D3:p2]" }
    ],

    // Markdown content for analysis (EXAMPLE: ~130 words - STAY UNDER 150!)
    "content": "### Investment Thesis\\n\\nWorld's largest franchisee with 1,200+ locations and strong unit economics ($1.2M average unit volume) [D3:p2]. Market leadership position in defensive QSR segment.\\n\\n### Key Strengths\\n\\n- Proven track record with 25% revenue CAGR [D3:p2]\\n- 40.5% EBITDA margins demonstrating operational excellence [D3:p2]\\n- Significant scale economies as largest franchisee\\n\\n### Critical Factors\\n\\n**Risk:** High leverage at 4.5x Debt/EBITDA and customer concentration (Top 3 = 45% revenue) [D3:p2]\\n\\n**Opportunity:** Geographic expansion and digital ordering capabilities offer clear growth path.",

    "citations": ["[D1:p2]", "[D3:p2]"]
    // OMIT "confidence" if you cannot determine it (do not set to null)
    // If you CAN determine confidence, set it as a float: "confidence": 0.9
  },
  {
    "key": "financial_performance",
    "title": "Financial Performance",

    "highlights": [
      {
        "type": "metric",
        "label": "Latest Revenue",
        "value": 111900000,
        "formatted": "$111.9M",
        "trend": "up",
        "trend_value": "13.4%",
        "year": 2023,
        "citation": "[D1:p5]"
      },
      {
        "type": "metric",
        "label": "Latest EBITDA",
        "value": 45300000,
        "formatted": "$45.3M",
        "year": 2023,
        "citation": "[D1:p5]"
      },
      {
        "type": "metric",
        "label": "EBITDA Margin",
        "value": 0.405,
        "formatted": "40.5%",
        "status": "strong",
        "citation": "[D1:p5]"
      }
    ],

    "key_metrics": [
      { "label": "Revenue CAGR", "value": "25%", "period": "3-year", "citation": "[D1:p5]" },
      { "label": "Margin Trend", "value": "Expanding", "status": "positive", "citation": "[D1:p5]" },
      { "label": "Free Cash Flow", "value": "$35M", "year": "2023", "citation": "[D1:p5]" }
    ],

    // STRUCTURED FINANCIAL DATA for tables/charts
    "financials": {
      "currency": "USD",  // MUST match top-level currency
      "fiscal_year_end": "December 31",
      "historical": [
        { "year": 2021, "revenue": 85200000, "ebitda": 28500000, "margin": 0.335, "citation": "[D1:p5]" },
        { "year": 2022, "revenue": 98700000, "ebitda": 38100000, "margin": 0.386, "citation": "[D1:p5]" },
        { "year": 2023, "revenue": 111900000, "ebitda": 45300000, "margin": 0.405, "citation": "[D1:p5]" }
      ],
      "metrics": {
        "rev_cagr": 0.25,
        "ebitda_margin_latest": 0.405,
        "citation": ["[D1:p5]"]
      }
    },

    "content": "### Revenue Growth\\n\\n**Historical Performance:**\\n- 2021: $85.2M\\n- 2022: $98.7M (+15.8%)\\n- 2023: $111.9M (+13.4%)\\n\\nThe company has demonstrated consistent revenue growth driven by same-store sales increases and new unit development [D1:p5].\\n\\n### Profitability\\n\\n**EBITDA Progression:**\\n- 2021: $28.5M (33.5% margin)\\n- 2022: $38.1M (38.6% margin)\\n- 2023: $45.3M (40.5% margin)\\n\\nMargin expansion reflects operational leverage and cost efficiencies [D1:p5].",

    "citations": ["[D1:p5]"]
  }
]

# ============================================================================
# SECTION COMPONENTS — How to Structure Each Section
# ============================================================================

Each section object includes:
- key: Section identifier (e.g., "executive_overview", "financial_performance")
- title: Display title
- highlights: Array of 3-5 MOST IMPORTANT data points (renders as visual cards)
  → Each highlight: {type, label, value, formatted?, citation}
  → Types: "company", "metric", "stat"
- key_metrics: Array of 3-6 supporting metrics (renders as pills)
  → Each metric: {label, value, citation, status?, period?}
- content: Markdown narrative with headings (###), bullets, citations
- citations: Array of all citations used in this section
- confidence: OPTIONAL float 0.0-1.0 (omit if uncertain, never null)

CONTENT FORMATTING — Well-Structured Markdown:
✅ Use headings (###), bold (**text**), bullets, numbers with units ($M, %, x)
✅ Include inline citations after quantitative claims: [D1:p2]
❌ Don't write raw numbers without formatting or context

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

## Management & Culture Section:
{
  "summary": "Overall assessment...",
  "key_people": [  // TOP 3-5 executives only (CEO, CFO, COO, etc.)
    {
      "name": "John Smith",
      "title": "Chief Executive Officer",
      "background": "1-2 sentence summary of experience and achievements",
      "tenure_years": 8  // INTEGER, omit if unknown
    }
  ],
  "strengths": ["Deep expertise...", "Proven track record..."],
  "gaps": ["Limited digital experience", "No CMO"],
  "citations": ["[D2:p20]"]
}

## Currency Detection (CRITICAL — Sets Top-Level Field):
- Look for: $, €, £, ¥ symbols OR USD, EUR, GBP codes in financials
- Set top-level "currency" AND section.financials.currency to SAME value
- If unclear: "UNKNOWN" and add to inconsistencies

# ============================================================================
# TOP-LEVEL SCHEMA — Complete Output Structure
# ============================================================================
Return STRICT JSON with these top-level keys:
{
  "currency": "USD",  // DETECT FROM DOCUMENT - Set this FIRST based on currency found in financials
  "sections": [
    // ... each section with key, title, content, etc.
    // financial_performance section will have embedded "financials" object
  ],
  "company_overview": {  // Optional top-level structured data
    "company_name": str, "industry": str, "headquarters": str, "description": str
  },
  "risks": [  // REQUIRED (may be empty array)
    {"description": str, "category": str, "severity": "High|Medium|Low", "citations": []}
  ],
  "opportunities": [  // REQUIRED (may be empty array)
    {"description": str, "category": str, "impact": "High|Medium|Low", "citations": []}
  ],
  "management": {  // Optional - See Management section format above
    "summary": str, "key_people": [...], "strengths": [...], "gaps": [...], "citations": []
  },
  "valuation": {  // Optional (only if include_valuation=true)
    "base_case": {"ev": float, "multiple": float, "irr": float, "assumptions": str, "citations": []}
  },
  "esg": {  // Optional
    "factors": [{"dimension": str, "status": "Positive|Neutral|Negative", "citation": str}],
    "overall": str
  },
  "next_steps": [
    {"priority": int, "action": str, "owner": str, "timeline_days": int}
  ],
  "inconsistencies": [str],  // List any data conflicts or ambiguities found
  "references": ["[D1:p2]", "[D1:p3]"],  // All unique citations
  "meta": {"version": 2}  // MUST be integer 2
}

NOTE: NO top-level "financials" object - it's embedded in financial_performance section

# ============================================================================
# ⚠️⚠️⚠️ CRITICAL REMINDER: GENERATE ALL 13 SECTIONS ⚠️⚠️⚠️
# ============================================================================

Your "sections" array in the JSON output MUST contain all 13 section objects:
[
  {"key": "executive_overview", "title": "Executive Overview", ...},
  {"key": "company_overview", "title": "Company Overview", ...},
  {"key": "market_competition", "title": "Market Competition", ...},
  {"key": "financial_performance", "title": "Financial Performance", ...},
  {"key": "unit_economics", "title": "Unit Economics", ...} (optional),
  {"key": "track_record_value_creation", "title": "Track Record & Value Creation", ...},
  {"key": "risks", "title": "Risks", ...},
  {"key": "opportunities", "title": "Opportunities", ...},
  {"key": "management_culture", "title": "Management & Culture", ...},
  {"key": "esg_snapshot", "title": "ESG Snapshot", ...},
  {"key": "valuation_scenarios", "title": "Valuation Scenarios", ...},
  {"key": "next_steps", "title": "Next Steps", ...},
  {"key": "inconsistencies", "title": "Inconsistencies", ...}
]

# ============================================================================
# FINAL CHECKLIST — Verify Before Responding
# ============================================================================
⚠️ CRITICAL: Count your sections array - it MUST have 13 objects (or 12 if unit_economics omitted)

Before generating your response, verify:
✓ Response starts with { (NO preamble, NO explanatory text)
✓ ⚠️ ALL 13 SECTIONS generated: executive_overview, company_overview, market_competition, financial_performance, unit_economics, track_record_value_creation, risks, opportunities, management_culture, esg_snapshot, valuation_scenarios, next_steps, inconsistencies
✓ ⚠️⚠️⚠️ CRITICAL: EACH section "content" = 100-150 words MAX (2-3 SHORT paragraphs)
✓ Total memo length: ~40-45K characters (readable in 5-7 minutes)
✓ Currency field set based on document (USD, EUR, GBP, etc.)
✓ All quantitative claims have inline citations [D1:p2]
✓ Financial_performance section has embedded "financials" object with ALL historical years
✓ Management_culture section has "key_people" array (3-5 top executives)
✓ Section content is well-formatted Markdown (###, bullets, bold, units)
✓ Bullet lists have 3-5 items MAX - TOP priorities only
✓ Each paragraph: 2-3 sentences MAX - no long blocks of text
✓ Numbers formatted with units ($M, %, x) in content, raw in structured data
✓ meta.version = 2 (integer, not "2" or 2.0)
✓ Response ends with } (NO trailing text)

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
