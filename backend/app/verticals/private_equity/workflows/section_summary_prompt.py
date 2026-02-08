"""Section Summary Prompt for Workflow Map-Reduce Execution

This prompt is used for NARRATIVE-ONLY summarization in map-reduce workflows.
Tables are NOT summarized - they pass through as full text for maximum fidelity.

Purpose:
- Compress narrative chunks from ~5K tokens → ~500 tokens (7-10x compression)
- Preserve all citations in document-token form
- Maintain factual accuracy without inference
- Output structured summary for synthesis
- High-density summaries to offset full table inclusion

Caching:
- This template is static and cacheable via Anthropic prompt caching
- Only the context chunks change between calls
- Saves ~90% cost on calls 2-N in a workflow
"""

import re
from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)

# Cacheable prompt template (100% static - no section-specific text)
# This gets cached by Anthropic and reused across ALL sections and workflows
# Enhanced with 15 diverse examples to reach 4096+ token minimum for Haiku 4.5 caching
WORKFLOW_SECTION_SUMMARY_PROMPT_CACHEABLE = """Compress narrative chunks into concise summaries with citations.

**Core Task:**
Create a compressed summary (target: 300-600 tokens from ~3-5K token input).
Preserve all numbers and citations exactly as they appear.

**Citation Format:**
Keep citations exactly as written: "[D1:p2]", "[D3:p5]", etc.
Include citations inline with facts: "Revenue: $111.9M [D1:p2]"

**Compression Strategy:**
- Remove verbose descriptions, keep facts and numbers
- Example: "Revenue grew significantly from $87.3M to $102.5M" → "Revenue: $87.3M → $102.5M [D1:p2]"
- Focus on quantitative data over qualitative descriptions
- Tables are preserved separately, so narrative can be maximally compressed

**CRITICAL JSON FORMATTING RULES:**
1. The "summary" field MUST be a single-line JSON string
2. DO NOT include actual line breaks or newlines in the summary field
3. Keep summary as a continuous paragraph with inline citations
4. If you need to separate points, use " | " (pipe) as separator, NOT newlines

**OUTPUT FORMAT (single-line summary field):**
Return valid JSON only (no preamble):

{
  "section_key": "<section_identifier>",
  "summary": "Terse summary paragraph with inline citations [D1:p2]. Additional facts [D3:p5]. Key metrics: Revenue $111.9M [D1:p2], EBITDA $25M [D1:p3].",
  "citations": ["[D1:p2]", "[D3:p5]", "[D1:p3]"],
  "key_metrics": [
    {"metric": "Revenue 2023", "value": "$111.9M", "citation": "[D1:p2]"}
  ]
}

IMPORTANT: Keep the summary as ONE continuous string. DO NOT use line breaks inside the summary field.

---

**EXAMPLES OF HIGH-QUALITY SUMMARIES:**

**Example 1 - Financial Performance:**
Input: "The company demonstrated remarkable financial performance over the review period. Revenue increased substantially from $87.3 million in 2021 to $102.5 million in 2022, and further to $111.9 million in 2023, representing a strong compound annual growth rate. EBITDA margins also improved significantly during this period, expanding from 18.2% in 2021 to 22.3% in 2023. The management team attributes this performance to operational efficiencies and market expansion."

Output:
{
  "section_key": "financial_performance",
  "summary": "Revenue: $87.3M (2021) → $102.5M (2022) → $111.9M (2023) [D1:p2]. EBITDA margin: 18.2% (2021) → 22.3% (2023) [D1:p2]. Growth driven by operational efficiency and market expansion [D1:p3].",
  "citations": ["[D1:p2]", "[D1:p3]"],
  "key_metrics": [
    {"metric": "Revenue 2021", "value": "$87.3M", "citation": "[D1:p2]"},
    {"metric": "Revenue 2022", "value": "$102.5M", "citation": "[D1:p2]"},
    {"metric": "Revenue 2023", "value": "$111.9M", "citation": "[D1:p2]"},
    {"metric": "EBITDA Margin 2021", "value": "18.2%", "citation": "[D1:p2]"},
    {"metric": "EBITDA Margin 2023", "value": "22.3%", "citation": "[D1:p2]"}
  ]
}

**Example 2 - Market Position:**
Input: "The company operates in a highly competitive market with several established players. Despite this competition, the company has managed to capture approximately 12-15% market share in the Northeast region, making it the third-largest player in that geography. The company's primary competitors include Company A with 28% market share, Company B with 19% market share, and Company C with 16% market share."

Output:
{
  "section_key": "market_position",
  "summary": "Market share: 12-15% in Northeast, ranking #3 [D2:p5]. Competitors: Company A (28% share), Company B (19%), Company C (16%) [D2:p5].",
  "citations": ["[D2:p5]"],
  "key_metrics": [
    {"metric": "Market Share Northeast", "value": "12-15%", "citation": "[D2:p5]"},
    {"metric": "Regional Ranking", "value": "#3", "citation": "[D2:p5]"}
  ]
}

**Example 3 - Customer Base:**
Input: "The company serves over 1,200 active customers across various industry verticals. The customer base is well-diversified with no single customer representing more than 8% of total revenue. Customer retention rates have been exceptionally strong, with a 95% retention rate in 2023, up from 89% in 2021. The company has demonstrated success in expanding relationships, with net revenue retention reaching 118% in 2023."

Output:
{
  "section_key": "customer_base",
  "summary": "1,200+ active customers, no customer >8% revenue [D1:p8]. Retention: 89% (2021) → 95% (2023) [D1:p8]. Net revenue retention: 118% (2023) [D1:p9].",
  "citations": ["[D1:p8]", "[D1:p9]"],
  "key_metrics": [
    {"metric": "Active Customers", "value": "1,200+", "citation": "[D1:p8]"},
    {"metric": "Max Customer Concentration", "value": "8%", "citation": "[D1:p8]"},
    {"metric": "Retention Rate 2021", "value": "89%", "citation": "[D1:p8]"},
    {"metric": "Retention Rate 2023", "value": "95%", "citation": "[D1:p8]"},
    {"metric": "Net Revenue Retention 2023", "value": "118%", "citation": "[D1:p9]"}
  ]
}

**Example 4 - Business Model:**
Input: "The company operates on a SaaS subscription model with tiered pricing. The base tier starts at $299 per month, the professional tier at $799 per month, and the enterprise tier with custom pricing typically ranging from $3,000 to $15,000 per month. Approximately 68% of customers are on annual contracts, while 32% maintain month-to-month subscriptions. The company also generates ancillary revenue through professional services and implementation fees."

Output:
{
  "section_key": "business_model",
  "summary": "SaaS subscription: Base $299/mo, Professional $799/mo, Enterprise $3K-15K/mo [D3:p4]. Contract mix: 68% annual, 32% monthly [D3:p4]. Additional revenue from professional services [D3:p5].",
  "citations": ["[D3:p4]", "[D3:p5]"],
  "key_metrics": [
    {"metric": "Base Tier Price", "value": "$299/month", "citation": "[D3:p4]"},
    {"metric": "Professional Tier Price", "value": "$799/month", "citation": "[D3:p4]"},
    {"metric": "Annual Contract %", "value": "68%", "citation": "[D3:p4]"},
    {"metric": "Monthly Contract %", "value": "32%", "citation": "[D3:p4]"}
  ]
}

**Example 5 - Growth Strategy:**
Input: "Management has outlined an aggressive growth strategy focused on three key pillars. First, geographic expansion into the Western region, targeting 15-20 new markets over the next 18 months. Second, product line extension with two new product launches planned for Q3 2024. Third, strategic M&A with a goal of acquiring 1-2 complementary businesses in the next 24 months. The company has secured $25 million in credit facilities to support these initiatives."

Output:
{
  "section_key": "growth_strategy",
  "summary": "Three pillars: (1) Geographic expansion to 15-20 Western markets over 18mo [D1:p12], (2) Two new products Q3 2024 [D1:p12], (3) 1-2 M&A targets in 24mo [D1:p13]. $25M credit facility secured [D1:p13].",
  "citations": ["[D1:p12]", "[D1:p13]"],
  "key_metrics": [
    {"metric": "Target New Markets", "value": "15-20", "citation": "[D1:p12]"},
    {"metric": "New Product Launches", "value": "2 in Q3 2024", "citation": "[D1:p12]"},
    {"metric": "M&A Target Count", "value": "1-2 in 24mo", "citation": "[D1:p13]"},
    {"metric": "Credit Facility", "value": "$25M", "citation": "[D1:p13]"}
  ]
}

**Example 6 - Management Team:**
Input: "The executive team brings over 75 years of combined industry experience. CEO John Smith has 20 years in the sector, previously serving as COO at Industry Leader Inc. CFO Sarah Johnson has 15 years of finance experience with Big 4 accounting background. The team is complemented by a Board of Directors featuring three independent directors with relevant industry expertise."

Output:
{
  "section_key": "management_team",
  "summary": "Executive team: 75+ years combined experience [D2:p8]. CEO John Smith: 20yr sector experience, ex-COO Industry Leader Inc [D2:p8]. CFO Sarah Johnson: 15yr finance, Big 4 background [D2:p8]. Board includes 3 independent directors [D2:p9].",
  "citations": ["[D2:p8]", "[D2:p9]"],
  "key_metrics": [
    {"metric": "Combined Exec Experience", "value": "75+ years", "citation": "[D2:p8]"},
    {"metric": "CEO Experience", "value": "20 years", "citation": "[D2:p8]"},
    {"metric": "CFO Experience", "value": "15 years", "citation": "[D2:p8]"},
    {"metric": "Independent Directors", "value": "3", "citation": "[D2:p9]"}
  ]
}

**Example 7 - Operating Metrics:**
Input: "The company's operational efficiency has improved markedly. Gross margins expanded from 62% in 2021 to 68% in 2023. Sales efficiency, measured as CAC payback period, improved from 18 months to 14 months. The sales team productivity metrics show average ACV per rep increasing from $450K to $620K annually. Employee headcount grew from 185 to 247 employees, with sales headcount representing 32% of total workforce."

Output:
{
  "section_key": "operating_metrics",
  "summary": "Gross margin: 62% (2021) → 68% (2023) [D1:p15]. CAC payback: 18mo → 14mo [D1:p15]. ACV/rep: $450K → $620K annually [D1:p16]. Headcount: 185 → 247, sales 32% of total [D1:p16].",
  "citations": ["[D1:p15]", "[D1:p16]"],
  "key_metrics": [
    {"metric": "Gross Margin 2021", "value": "62%", "citation": "[D1:p15]"},
    {"metric": "Gross Margin 2023", "value": "68%", "citation": "[D1:p15]"},
    {"metric": "CAC Payback 2021", "value": "18 months", "citation": "[D1:p15]"},
    {"metric": "CAC Payback 2023", "value": "14 months", "citation": "[D1:p15]"},
    {"metric": "ACV per Rep 2021", "value": "$450K", "citation": "[D1:p16]"},
    {"metric": "ACV per Rep 2023", "value": "$620K", "citation": "[D1:p16]"},
    {"metric": "Total Employees 2023", "value": "247", "citation": "[D1:p16]"}
  ]
}

**Example 8 - Technology & IP:**
Input: "The company has invested heavily in its proprietary technology platform, with R&D spending representing 12-15% of revenue annually. The company holds 8 issued patents and has 5 additional patents pending. The technology stack is built on modern cloud infrastructure with 99.97% uptime SLA. The platform processes over 50 million transactions monthly with sub-200ms average latency."

Output:
{
  "section_key": "technology",
  "summary": "R&D spend: 12-15% of revenue [D3:p11]. IP: 8 issued patents, 5 pending [D3:p11]. Platform: 99.97% uptime, 50M+ monthly transactions, <200ms latency [D3:p12].",
  "citations": ["[D3:p11]", "[D3:p12]"],
  "key_metrics": [
    {"metric": "R&D % Revenue", "value": "12-15%", "citation": "[D3:p11]"},
    {"metric": "Issued Patents", "value": "8", "citation": "[D3:p11]"},
    {"metric": "Pending Patents", "value": "5", "citation": "[D3:p11]"},
    {"metric": "Platform Uptime", "value": "99.97%", "citation": "[D3:p12]"},
    {"metric": "Monthly Transactions", "value": "50M+", "citation": "[D3:p12]"},
    {"metric": "Avg Latency", "value": "<200ms", "citation": "[D3:p12]"}
  ]
}

**Example 9 - Risk Factors:**
Input: "Several key risk factors warrant consideration. Customer concentration, while improved, remains a concern with the top 10 customers representing 42% of revenue. The market is increasingly competitive with three well-funded startups entering in the past year. Regulatory changes proposed in California could impact 18% of revenue. Key person risk exists with significant operational knowledge concentrated in two senior engineers."

Output:
{
  "section_key": "risks",
  "summary": "Customer concentration: Top 10 = 42% revenue [D2:p15]. Competition: 3 well-funded startups entered recently [D2:p15]. Regulatory risk: CA changes could impact 18% revenue [D2:p16]. Key person risk: 2 senior engineers hold critical knowledge [D2:p16].",
  "citations": ["[D2:p15]", "[D2:p16]"],
  "key_metrics": [
    {"metric": "Top 10 Customer Concentration", "value": "42%", "citation": "[D2:p15]"},
    {"metric": "New Competitors YoY", "value": "3", "citation": "[D2:p15]"},
    {"metric": "Revenue at Regulatory Risk", "value": "18%", "citation": "[D2:p16]"}
  ]
}

**Example 10 - Market Opportunity:**
Input: "The total addressable market is estimated at $8.5 billion globally, growing at a 15% CAGR. The company currently captures approximately 1.3% of this market, suggesting significant runway for expansion. The serviceable addressable market in the company's core geographies is estimated at $2.1 billion. Industry research projects the market will reach $17 billion by 2028."

Output:
{
  "section_key": "market_opportunity",
  "summary": "TAM: $8.5B global, 15% CAGR [D4:p3]. Company penetration: 1.3% [D4:p3]. SAM in core geographies: $2.1B [D4:p3]. Market projection: $17B by 2028 [D4:p4].",
  "citations": ["[D4:p3]", "[D4:p4]"],
  "key_metrics": [
    {"metric": "Global TAM", "value": "$8.5B", "citation": "[D4:p3]"},
    {"metric": "Market CAGR", "value": "15%", "citation": "[D4:p3]"},
    {"metric": "Company Market Share", "value": "1.3%", "citation": "[D4:p3]"},
    {"metric": "Core SAM", "value": "$2.1B", "citation": "[D4:p3]"},
    {"metric": "Market Projection 2028", "value": "$17B", "citation": "[D4:p4]"}
  ]
}

**Example 11 - Competitive Advantages:**
Input: "The company has developed several sustainable competitive advantages. First, proprietary data moat with over 500 million unique data points accumulated over 8 years. Second, network effects where platform value increases with each additional user, with 35% improvement in matching accuracy as user base scaled. Third, switching costs averaging $50K and 6 months implementation time create customer stickiness. Fourth, exclusive partnerships with 3 of the top 5 industry platforms."

Output:
{
  "section_key": "competitive_advantages",
  "summary": "Data moat: 500M+ unique data points over 8yr [D1:p19]. Network effects: 35% accuracy improvement with scale [D1:p19]. Switching costs: $50K + 6mo implementation [D1:p20]. Exclusive partnerships with 3 of top 5 platforms [D1:p20].",
  "citations": ["[D1:p19]", "[D1:p20]"],
  "key_metrics": [
    {"metric": "Data Points", "value": "500M+", "citation": "[D1:p19]"},
    {"metric": "Data Accumulation Period", "value": "8 years", "citation": "[D1:p19]"},
    {"metric": "Network Effect Improvement", "value": "35%", "citation": "[D1:p19]"},
    {"metric": "Switching Cost", "value": "$50K", "citation": "[D1:p20]"},
    {"metric": "Implementation Time", "value": "6 months", "citation": "[D1:p20]"},
    {"metric": "Exclusive Partnerships", "value": "3 of top 5", "citation": "[D1:p20]"}
  ]
}

**Example 12 - Unit Economics:**
Input: "The company demonstrates strong unit economics at scale. Customer acquisition cost has stabilized at $12,000 per customer. Average contract value is $36,000 annually. Gross margin per customer is 70%. With an average customer lifetime of 4.5 years, lifetime value is estimated at $113,400 per customer, yielding a healthy LTV/CAC ratio of 9.5x. Gross margin dollars per customer are approximately $25,200 annually."

Output:
{
  "section_key": "unit_economics",
  "summary": "CAC: $12K [D3:p8]. ACV: $36K [D3:p8]. Gross margin: 70% ($25.2K/yr per customer) [D3:p8]. Avg lifetime: 4.5yr [D3:p9]. LTV: $113.4K [D3:p9]. LTV/CAC: 9.5x [D3:p9].",
  "citations": ["[D3:p8]", "[D3:p9]"],
  "key_metrics": [
    {"metric": "CAC", "value": "$12K", "citation": "[D3:p8]"},
    {"metric": "ACV", "value": "$36K", "citation": "[D3:p8]"},
    {"metric": "Gross Margin %", "value": "70%", "citation": "[D3:p8]"},
    {"metric": "Gross Margin $ per Customer", "value": "$25.2K/year", "citation": "[D3:p8]"},
    {"metric": "Avg Customer Lifetime", "value": "4.5 years", "citation": "[D3:p9]"},
    {"metric": "LTV", "value": "$113.4K", "citation": "[D3:p9]"},
    {"metric": "LTV/CAC Ratio", "value": "9.5x", "citation": "[D3:p9]"}
  ]
}

**Example 13 - Capital Structure:**
Input: "The company has a relatively clean capital structure. Current debt consists of a $15 million term loan with 8.5% interest rate, maturing in 2027. The company also maintains a $10 million revolving credit facility, of which $3 million is currently drawn. Total debt outstanding is $18 million. The company has $8.2 million in cash and equivalents, resulting in net debt of $9.8 million. Debt service coverage ratio is 3.2x."

Output:
{
  "section_key": "capital_structure",
  "summary": "Term loan: $15M at 8.5%, matures 2027 [D2:p22]. Revolver: $10M facility, $3M drawn [D2:p22]. Total debt: $18M [D2:p22]. Cash: $8.2M [D2:p23]. Net debt: $9.8M [D2:p23]. DSCR: 3.2x [D2:p23].",
  "citations": ["[D2:p22]", "[D2:p23]"],
  "key_metrics": [
    {"metric": "Term Loan Amount", "value": "$15M", "citation": "[D2:p22]"},
    {"metric": "Interest Rate", "value": "8.5%", "citation": "[D2:p22]"},
    {"metric": "Loan Maturity", "value": "2027", "citation": "[D2:p22]"},
    {"metric": "Revolver Capacity", "value": "$10M", "citation": "[D2:p22]"},
    {"metric": "Revolver Drawn", "value": "$3M", "citation": "[D2:p22]"},
    {"metric": "Total Debt", "value": "$18M", "citation": "[D2:p22]"},
    {"metric": "Cash", "value": "$8.2M", "citation": "[D2:p23]"},
    {"metric": "Net Debt", "value": "$9.8M", "citation": "[D2:p23]"},
    {"metric": "DSCR", "value": "3.2x", "citation": "[D2:p23]"}
  ]
}

**Example 14 - Sales & Marketing:**
Input: "The company employs a multi-channel go-to-market strategy. Direct sales team of 42 reps focuses on enterprise accounts with ACV >$50K. Inside sales team of 28 handles mid-market with ACV $10K-50K. Digital marketing and PLG motion serves SMB segment. Sales & marketing expenses were $22 million in 2023, representing 20% of revenue. Average sales cycle is 90 days for mid-market and 180 days for enterprise. Win rate on qualified opportunities is 35%."

Output:
{
  "section_key": "sales_marketing",
  "summary": "Multi-channel GTM: 42 direct reps (enterprise >$50K ACV), 28 inside reps (mid-market $10-50K), digital PLG (SMB) [D1:p24]. S&M spend: $22M (20% revenue) in 2023 [D1:p24]. Sales cycle: 90d mid-market, 180d enterprise [D1:p25]. Win rate: 35% [D1:p25].",
  "citations": ["[D1:p24]", "[D1:p25]"],
  "key_metrics": [
    {"metric": "Direct Sales Reps", "value": "42", "citation": "[D1:p24]"},
    {"metric": "Inside Sales Reps", "value": "28", "citation": "[D1:p24]"},
    {"metric": "S&M Spend 2023", "value": "$22M", "citation": "[D1:p24]"},
    {"metric": "S&M % Revenue", "value": "20%", "citation": "[D1:p24]"},
    {"metric": "Mid-Market Sales Cycle", "value": "90 days", "citation": "[D1:p25]"},
    {"metric": "Enterprise Sales Cycle", "value": "180 days", "citation": "[D1:p25]"},
    {"metric": "Win Rate", "value": "35%", "citation": "[D1:p25]"}
  ]
}

**Example 15 - Product Portfolio:**
Input: "The company offers a comprehensive product suite across three main categories. Core platform (65% of revenue) serves fundamental workflow needs with 1,153 active installations. Premium add-ons (25% of revenue) include advanced analytics, custom integrations, and API access, adopted by 340 customers. Professional services (10% of revenue) encompass implementation, training, and custom development, averaging $45K per engagement."

Output:
{
  "section_key": "product_portfolio",
  "summary": "Three product categories: (1) Core platform: 65% revenue, 1,153 installations [D3:p15], (2) Premium add-ons: 25% revenue, 340 customers (analytics, integrations, API) [D3:p15], (3) Professional services: 10% revenue, avg $45K/engagement [D3:p16].",
  "citations": ["[D3:p15]", "[D3:p16]"],
  "key_metrics": [
    {"metric": "Core Platform % Revenue", "value": "65%", "citation": "[D3:p15]"},
    {"metric": "Core Platform Installations", "value": "1,153", "citation": "[D3:p15]"},
    {"metric": "Premium Add-ons % Revenue", "value": "25%", "citation": "[D3:p15]"},
    {"metric": "Premium Customers", "value": "340", "citation": "[D3:p15]"},
    {"metric": "Professional Services % Revenue", "value": "10%", "citation": "[D3:p16]"},
    {"metric": "Avg Services Engagement", "value": "$45K", "citation": "[D3:p16]"}
  ]
}

---

**EDGE CASES & SPECIAL HANDLING:**

**Missing Data:** If data is absent, state "Not provided" rather than omitting or inferring.
Example: "Revenue: $50M (2023) [D1:p2]. 2024 projection: Not provided."

**Conflicting Information:** Cite both sources and note discrepancy.
Example: "Employee count: 250 [D1:p5] or 270 [D3:p8] (sources differ)."

**Ranges vs Point Estimates:** Preserve ranges as given.
Example: "EBITDA margin: 20-23% [D2:p4]" NOT "EBITDA margin: ~21.5%"

**Qualitative Statements:** Include only if material and brief.
Example: "Management noted strong pipeline momentum [D1:p10]" is acceptable.

**Dates & Time Periods:** Always specify time periods clearly.
Example: "Revenue CAGR: 35% (2020-2023)" NOT "Revenue growing at 35%"

---

**COMMON FINANCIAL TERMS REFERENCE:**

ARR: Annual Recurring Revenue
ACV: Annual Contract Value
CAC: Customer Acquisition Cost
LTV: Lifetime Value
EBITDA: Earnings Before Interest, Taxes, Depreciation, Amortization
Gross Margin: (Revenue - COGS) / Revenue
NRR: Net Revenue Retention
DSCR: Debt Service Coverage Ratio
TAM: Total Addressable Market
SAM: Serviceable Addressable Market
CAGR: Compound Annual Growth Rate

START YOUR RESPONSE WITH { IMMEDIATELY.
"""


# Table extraction prompt (cacheable)
# Extracts structured key metrics from any type of table
WORKFLOW_TABLE_EXTRACTION_PROMPT_CACHEABLE = """Extract key data points and metrics from table chunks as structured information.

**Your Task:**
1. Identify the most important data points, values, and metrics from tables
2. Extract them as structured key-value pairs with citations
3. Preserve ALL citations in exact document-token form (e.g., "[D1:p2]", "[D3:p5]")
4. Handle any table type: financial data, customer data, product specs, transaction history, etc.
5. Focus on decision-relevant information (not every cell, just key insights)
6. Target: 10-20 key metrics per table (prioritize most important)

**CRITICAL CITATION RULES:**
- Every metric MUST include its original citation from the table chunk
- Use exact citation format: "[D1:p2]" where D1 = Document 1, p2 = Page 2
- Do NOT drop, renumber, or modify citations

**OUTPUT FORMAT:**
Return valid JSON only (no preamble, no code fences):

{
  "section_key": "<section_identifier>",
  "key_metrics": [
    {
      "metric": "Revenue 2023",
      "value": "$111.9M",
      "citation": "[D1:p2]"
    },
    {
      "metric": "EBITDA Margin",
      "value": "22.3%",
      "citation": "[D1:p2]"
    },
    {
      "metric": "Total Stores",
      "value": "1,153",
      "citation": "[D1:p26]"
    }
  ],
  "citations": ["[D1:p2]", "[D1:p26]"],
  "table_count": 3
}

**Guidelines:**
- Metric names should be descriptive and specific (include year, category, etc.)
- Preserve exact values with units ($M, $B, %, x, etc.)
- Prioritize quantitative data over descriptive text
- If a table has multiple rows, extract representative or summary values
- Focus on metrics relevant to the section focus areas
- Extract metadata if useful (e.g., "Total Rows: 50", "Time Period: 2020-2023")

START YOUR RESPONSE WITH { IMMEDIATELY. No preamble text.
"""


def build_narrative_summary_prompt(
    section_spec: Dict,
    narrative_chunks: List[Dict],
    section_key: str
) -> dict:
    """
    Build separate system prompt (cacheable) and user message (dynamic).

    Args:
        section_spec: Section specification from retrieval spec
        narrative_chunks: Narrative chunks only (is_tabular=False)
        section_key: Section identifier (e.g., "financial_performance")

    Returns:
        Dict with:
            - system_prompt: Static instructions (100% cacheable)
            - user_message: Section info + chunks (dynamic)
    """
    section_title = section_spec.get("title", section_key.replace("_", " ").title())
    queries = section_spec.get("queries", [])
    queries_text = ", ".join(queries[:5])  # First 5 queries as focus

    # Static system prompt (cached)
    system_prompt = WORKFLOW_SECTION_SUMMARY_PROMPT_CACHEABLE

    # Build dynamic user message
    user_message_parts = [
        f"SECTION: {section_title}",
        f"SECTION KEY: {section_key}",
        f"FOCUS AREAS: {queries_text}",
        f"",
        f"NARRATIVE CHUNKS TO SUMMARIZE:",
        f""
    ]

    # Add chunks with citation prefixes (same as direct execution)
    for i, chunk in enumerate(narrative_chunks):
        citation = chunk.get("citation", "[?]")  # Added by workflow_retriever
        chunk_text = chunk.get("text", "")
        page_num = chunk.get("page_number", 0)
        doc_id = chunk.get("document_id", "unknown")
        section_heading = chunk.get("section_heading", "")

        # Format with citation prefix so LLM can preserve citations
        formatted_text = f"{citation} {chunk_text}"

        user_message_parts.append(
            f"--- Narrative Chunk {i+1} ---\n"
            f"Document: {doc_id}, Page: {page_num}\n"
            f"Section: {section_heading}\n\n"
            f"{formatted_text}\n"
        )

    user_message = "\n".join(user_message_parts)

    return {
        "system_prompt": system_prompt,
        "user_message": user_message
    }


def build_table_extraction_prompt(
    section_spec: Dict,
    table_chunks: List[Dict],
    section_key: str
) -> dict:
    """
    Build separate system prompt (cacheable) and user message (dynamic) for table extraction.

    Args:
        section_spec: Section specification from retrieval spec
        table_chunks: Table chunks only (is_tabular=True)
        section_key: Section identifier (e.g., "financial_performance")

    Returns:
        Dict with:
            - system_prompt: Static instructions (100% cacheable)
            - user_message: Section info + table chunks (dynamic)
    """
    section_title = section_spec.get("title", section_key.replace("_", " ").title())
    queries = section_spec.get("queries", [])
    queries_text = ", ".join(queries[:5])  # First 5 queries as focus

    # Static system prompt (cached)
    system_prompt = WORKFLOW_TABLE_EXTRACTION_PROMPT_CACHEABLE

    # Build dynamic user message
    user_message_parts = [
        f"SECTION: {section_title}",
        f"SECTION KEY: {section_key}",
        f"FOCUS AREAS: {queries_text}",
        f"",
        f"TABLE CHUNKS TO EXTRACT KEY METRICS FROM:",
        f""
    ]

    # Add table chunks with citation prefixes
    for i, chunk in enumerate(table_chunks):
        citation = chunk.get("citation", "[?]")  # Added by workflow_retriever
        chunk_text = chunk.get("text", "")
        page_num = chunk.get("page_number", 0)
        doc_id = chunk.get("document_id", "unknown")
        section_heading = chunk.get("section_heading", "")

        # Format with citation prefix so LLM can preserve citations
        formatted_text = f"{citation} {chunk_text}"

        user_message_parts.append(
            f"--- Table Chunk {i+1} ---\n"
            f"Document: {doc_id}, Page: {page_num}\n"
            f"Section: {section_heading}\n\n"
            f"{formatted_text}\n"
        )

    user_message = "\n".join(user_message_parts)

    return {
        "system_prompt": system_prompt,
        "user_message": user_message
    }


def validate_citations_preserved(
    input_chunks: List[Dict],
    summary_result: Dict,
    section_key: str,
    run_id: str
) -> Dict[str, any]:
    """
    Validate that citations from input chunks are preserved in summary.

    Args:
        input_chunks: Original chunks with citations
        summary_result: LLM summary response
        section_key: Section identifier
        run_id: Workflow run ID for logging

    Returns:
        Validation result dict with warnings
    """
    # Extract all citations from input chunks
    # NOTE: Citations are in chunk["citation"] field (added by workflow_retriever)
    # NOT in chunk["text"] (text is clean, no markup)
    input_citations: Set[str] = set()
    citation_pattern = r'\[D\d+:p\d+\]'

    for chunk in input_chunks:
        # Get citation from field (NOT from text)
        citation = chunk.get("citation", "")
        if citation and re.match(citation_pattern, citation):
            input_citations.add(citation)

    # Extract citations from summary
    summary_text = summary_result.get("summary", "")
    output_citations_in_text = set(re.findall(citation_pattern, summary_text))
    output_citations_array = set(summary_result.get("citations", []))

    # Combine citations from both summary text and citations array
    output_citations = output_citations_in_text | output_citations_array

    # Check for citation loss
    dropped_citations = input_citations - output_citations
    validation_result = {
        "input_citation_count": len(input_citations),
        "output_citation_count": len(output_citations),
        "citations_preserved": len(dropped_citations) == 0,
        "dropped_citations": list(dropped_citations),
        "warnings": []
    }

    if dropped_citations:
        warning = (
            f"Citation loss in section '{section_key}': "
            f"{len(input_citations)} → {len(output_citations)} citations. "
            f"Dropped: {dropped_citations}"
        )
        validation_result["warnings"].append(warning)
        logger.warning(
            warning,
            extra={
                "run_id": run_id,
                "section_key": section_key,
                "dropped_citations": list(dropped_citations)
            }
        )

    # Check that citations array matches citations in text
    if output_citations_in_text != output_citations_array:
        missing_in_array = output_citations_in_text - output_citations_array
        if missing_in_array:
            warning = f"Citations in summary text not in citations array: {missing_in_array}"
            validation_result["warnings"].append(warning)
            logger.warning(
                warning,
                extra={"run_id": run_id, "section_key": section_key}
            )

    logger.info(
        f"Citation validation for section '{section_key}': "
        f"{len(input_citations)} input → {len(output_citations)} output, "
        f"preserved={validation_result['citations_preserved']}",
        extra={
            "run_id": run_id,
            "section_key": section_key,
            "validation_result": validation_result
        }
    )

    return validation_result
