"""Red Flags workflow template definition.

Version: 1 (upgraded structure)
Purpose: Produce aggregated multi-category risk indicators with severity, confidence & mitigation.

JSON Contract (summary):
{
    categories: [
        {
            name: str,
            items: [ { description, severity, citation: [tokens], confidence?, recommended_action? } ],
            category_risk_summary: str,
            category_score: int(1-5)
        }
    ],
    overall: {
        top_red_flags: [str],
        risk_heatmap: { CategoryName: SeverityBucket },
        mitigation_priorities: [ { risk, priority, owner } ],
        summary: str
    }
}

Edge Cases:
- Category may have zero items; still include with empty items array & score reflecting absence (e.g., 1).
- Duplicate risks across categories must be merged into one primary category; description can cross-reference others.
- citation arrays must only contain tokens present in context; invalid tokens should be pruned upstream.
- confidence omitted entirely if return_confidence false.
- severity scale switches based on severity_scale variable (basic vs extended) but schema is permissive; normalization handled upstream.
"""

RED_FLAGS_PROMPT = """
Generate a comprehensive red flags assessment for {{company_name}}.

Context:
You are assisting private equity diligence. Go beyond a checklist: surface integrity, alignment, concentration, governance and unrealistic claims.

Dynamic Category Inclusion (driven by variables):
- Always include: Financial, Operational, Market, Legal/Compliance, Strategic.
- Include ESG if {{include_esg}} is true.
- Include Management & Culture if {{include_management_culture}} is true.
- Include Technology & Data if {{include_technology_data}} is true.
- Always include Track Record Integrity if focus_area == "financial" or focus_area == "all".

Instructions per category:
Identify 0–{{max_items_per_category}} material red flags. Each item MUST be evidence-based and cite one or MORE source chunks using bracket form [D#:p#]. Avoid generic statements. If an item depends on multiple facts, include multiple citations.

Severity scale:
If {{severity_scale}} == "extended" use one of: Low, Moderate, High, Critical.
If {{severity_scale}} == "basic" use: Low, Medium, High.

Each item fields:
- description (≤ 40 words)
- severity
- citation: array ["[D1:p2]", ...]
- confidence (optional if return_confidence true)
- recommended_action

Category level fields:
- name
- items
- category_risk_summary (≤ 120 words)
- category_score (1–5)

Overall section:
- top_red_flags
- risk_heatmap
- mitigation_priorities
- summary (≤ 180 words, no inline citations)

Return STRICT JSON only:
{
  "categories": [ { "name": "Financial", "items": [ { "description": "text", "severity": "High", "citation": ["[D1:p2]"], "confidence": "Medium", "recommended_action": "text" } ], "category_risk_summary": "text", "category_score": 3 } ],
  "overall": { "top_red_flags": ["text"], "risk_heatmap": {"Financial": "High"}, "mitigation_priorities": [ { "risk": "text", "priority": 1, "owner": "Management" } ], "summary": "text" }
}
""".strip()

RED_FLAGS_SCHEMA = {
    "variables": [
        {"name": "company_name", "type": "string", "required": True},
        {"name": "focus_area", "type": "enum", "choices": ["financial", "operational", "market", "legal", "strategic", "all"], "default": "all"},
        {"name": "include_esg", "type": "boolean", "default": True},
        {"name": "include_management_culture", "type": "boolean", "default": True},
        {"name": "include_technology_data", "type": "boolean", "default": True},
        {"name": "max_items_per_category", "type": "integer", "default": 5, "min": 1, "max": 12},
        {"name": "severity_scale", "type": "enum", "choices": ["basic", "extended"], "default": "extended"},
        {"name": "return_confidence", "type": "boolean", "default": True},
    ]
}

TEMPLATE = {
    "name": "Red Flags Summary",
    "category": "diligence",
    "description": "Aggregated risk indicators across key categories",
    "prompt_template": RED_FLAGS_PROMPT,
    "variables_schema": RED_FLAGS_SCHEMA,
    "output_format": "json",
    "min_documents": 1,
    "max_documents": 10,
    "version": 1,
}
