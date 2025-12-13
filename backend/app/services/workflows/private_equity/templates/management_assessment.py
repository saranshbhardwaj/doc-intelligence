"""Management Assessment workflow template definition.

Version: 1
Purpose: Comprehensive evaluation of management team, organizational structure, and leadership capabilities for PE diligence.

JSON Contract (summary):
{
    executive_summary: { overall_rating, key_strengths[], critical_gaps[], recommendation },
    leadership_team: [
        {
            name, role, tenure_years, background_summary,
            strengths[], weaknesses[], rating, succession_risk,
            citation[]
        }
    ],
    organizational_structure: {
        org_chart_summary, headcount, key_departments[],
        span_of_control_issues[], structural_gaps[], citation[]
    },
    compensation_alignment: {
        equity_ownership[], incentive_structure,
        alignment_score, concerns[], citation[]
    },
    culture_assessment: {
        cultural_strengths[], cultural_risks[],
        employee_retention_metrics, citation[]
    },
    succession_planning: {
        key_person_dependencies[], backup_readiness,
        succession_risks[], mitigation_plans[], citation[]
    },
    capability_gaps: [
        { gap_area, severity, impact_on_growth, recommended_hire, citation[] }
    ],
    board_governance: {
        board_composition, independence_score,
        governance_strengths[], governance_gaps[], citation[]
    },
    recommendations: [
        { priority, action, rationale, timeline, owner }
    ],
    meta: { version: 1 }
}

Edge Cases:
- Limited biographical data: Focus on available info, flag gaps in capability_gaps
- Missing compensation data: Note in concerns[], mark alignment_score as "Unknown"
- No org chart: Infer structure from text, flag in structural_gaps
- Single-person leadership: Flag as critical succession risk
- Conflicting information: Document in executive_summary.recommendation
"""

MANAGEMENT_ASSESSMENT_PROMPT = """
Generate a comprehensive management team assessment for {{company_name}}.

Objective:
Evaluate the leadership team's capability to execute the business plan and drive value creation post-acquisition.
Focus on: talent quality, organizational structure, compensation alignment, succession risks, and critical capability gaps.

Dynamic Configuration (driven by variables):
- Include detailed compensation analysis if {{include_compensation}} is true
- Include board/governance assessment if {{include_board_governance}} is true
- Include cultural assessment if {{include_culture}} is true
- Focus depth: {{assessment_depth}} ("summary" = high-level, "detailed" = deep-dive)

Instructions:

SECTION 1: EXECUTIVE SUMMARY
Provide overall assessment with actionable recommendation.

Format:
"executive_summary": {
    "overall_rating": "Strong|Adequate|Weak",
    "key_strengths": ["Seasoned CFO with prior PE-backed experience", "Strong bench in sales leadership"],
    "critical_gaps": ["No dedicated VP of Operations", "CEO lacks industry experience"],
    "recommendation": "Team is adequate but requires 2-3 strategic hires pre-close. Succession planning needed for CFO."
}

SECTION 2: LEADERSHIP TEAM ANALYSIS
For each C-level and VP-level executive, assess:
- Background & tenure
- Key strengths (functional expertise, industry experience, track record)
- Weaknesses or gaps
- Individual rating (Strong/Adequate/Weak)
- Succession risk (High/Medium/Low)

ALL assessments must cite evidence from documents (bios, org charts, presentations).

Format:
"leadership_team": [
    {
        "name": "John Smith",
        "role": "CEO",
        "tenure_years": 8,
        "background_summary": "Former VP at BigCo, 15 years in SaaS",
        "strengths": ["Deep customer relationships", "Proven ability to scale teams"],
        "weaknesses": ["Limited M&A experience", "No prior PE-backed company experience"],
        "rating": "Adequate",
        "succession_risk": "High",
        "citation": ["[D1:p12]", "[D2:p5]"]
    }
]

SECTION 3: ORGANIZATIONAL STRUCTURE
Analyze org structure, headcount allocation, and structural issues.

Extract or infer:
- Total headcount (if available)
- Key departments & reporting lines
- Span of control issues (e.g., CEO with 15 direct reports)
- Structural gaps (e.g., no dedicated product management layer)

Format:
"organizational_structure": {
    "org_chart_summary": "Flat structure with 12 direct reports to CEO",
    "headcount": 150,
    "key_departments": ["Sales (40)", "Engineering (60)", "G&A (50)"],
    "span_of_control_issues": ["CEO has 12 direct reports; best practice is 5-7"],
    "structural_gaps": ["No VP of Product; product decisions made by CEO"],
    "citation": ["[D3:p8]"]
}

SECTION 4: COMPENSATION & ALIGNMENT (Conditional: {{include_compensation}})
Assess equity ownership and incentive structures.

Key questions:
- Do executives have meaningful equity ownership? (Skin in the game)
- Are incentives tied to value-creation metrics (EBITDA, revenue growth, etc.)?
- Any red flags (guaranteed bonuses, retention issues)?

Format:
"compensation_alignment": {
    "equity_ownership": ["CEO: 15%", "CFO: 5%", "CTO: 3%"],
    "incentive_structure": "Annual bonuses tied to EBITDA targets; no long-term equity plan",
    "alignment_score": "Moderate",
    "concerns": ["No equity refresh plan post-acquisition", "Retention risk for CTO"],
    "citation": ["[D4:p20]"]
}

SECTION 5: CULTURE ASSESSMENT (Conditional: {{include_culture}})
Evaluate cultural strengths, risks, and employee retention.

Look for:
- Cultural values (innovation, customer-first, execution-focused, etc.)
- Employee retention metrics (turnover rate, tenure distribution)
- Cultural risks (toxic behaviors, siloed teams, burnout)

Format:
"culture_assessment": {
    "cultural_strengths": ["Customer-first mentality", "High employee engagement scores"],
    "cultural_risks": ["Engineering team siloed from sales", "High turnover in sales org (30% annually)"],
    "employee_retention_metrics": "Average tenure: 3.5 years; 18% annual turnover",
    "citation": ["[D2:p15]", "[D5:p10]"]
}

SECTION 6: SUCCESSION PLANNING
Identify key person dependencies and succession risks.

Critical questions:
- Are there single points of failure? (e.g., founder-CEO with no successor)
- Is there a bench of internal promotable talent?
- What are succession timelines for key roles?

Format:
"succession_planning": {
    "key_person_dependencies": ["CEO is sole relationship owner for top 5 customers (60% of revenue)"],
    "backup_readiness": "Limited internal bench; VP of Sales could step into CEO role but needs 12-18 months development",
    "succession_risks": ["CFO retiring in 18 months; no internal successor"],
    "mitigation_plans": ["Hire VP of Finance within 6 months", "Transition customer relationships to sales team"],
    "citation": ["[D1:p25]"]
}

SECTION 7: CAPABILITY GAPS
Identify functional or skill gaps that must be addressed.

Consider:
- Missing roles (e.g., VP of Operations, Chief Revenue Officer)
- Skill deficits (e.g., no M&A experience, no international expansion experience)
- Capacity constraints (e.g., finance team too small to scale)

Format:
"capability_gaps": [
    {
        "gap_area": "VP of Operations",
        "severity": "High",
        "impact_on_growth": "Critical for scaling operations beyond $100M revenue",
        "recommended_hire": "Hire experienced operations executive with supply chain expertise",
        "citation": ["[D3:p12]"]
    }
]

SECTION 8: BOARD & GOVERNANCE (Conditional: {{include_board_governance}})
Assess board composition and governance practices.

Key questions:
- Board composition (insiders vs. independents)
- Expertise gaps on board (e.g., no tech expertise, no finance expertise)
- Governance strengths/gaps (audit committee, comp committee, etc.)

Format:
"board_governance": {
    "board_composition": "5 members: 2 founders, 1 investor rep, 2 independents",
    "independence_score": "Moderate",
    "governance_strengths": ["Strong audit committee oversight", "Quarterly board meetings"],
    "governance_gaps": ["No compensation committee", "Board lacks industry expertise"],
    "citation": ["[D6:p3]"]
}

SECTION 9: RECOMMENDATIONS
Prioritized action items for improving management/org pre-close or within first 100 days.

Format:
"recommendations": [
    {
        "priority": 1,
        "action": "Hire VP of Operations",
        "rationale": "Critical gap for scaling operations; CEO cannot continue to manage operations directly",
        "timeline": "Pre-close",
        "owner": "Investor"
    },
    {
        "priority": 2,
        "action": "Implement equity refresh plan for key executives",
        "rationale": "Retention risk for CTO and VP of Sales without equity upside",
        "timeline": "Within 30 days post-close",
        "owner": "Joint"
    }
]

SECTION 10: METADATA
"meta": { "version": 1 }

CRITICAL RULES:
1. ALL assessments and claims must cite supporting evidence using [D#:p#] format
2. Avoid generic platitudes; provide specific, actionable insights
3. Flag data gaps explicitly rather than making assumptions
4. Balance positive and negative feedback; be objective
5. Return STRICT JSON only, no commentary outside JSON structure

Return JSON with structure:
{
    "executive_summary": {...},
    "leadership_team": [...],
    "organizational_structure": {...},
    "compensation_alignment": {...},
    "culture_assessment": {...},
    "succession_planning": {...},
    "capability_gaps": [...],
    "board_governance": {...},
    "recommendations": [...],
    "meta": {...}
}
""".strip()

MANAGEMENT_ASSESSMENT_SCHEMA = {
    "variables": [
        {"name": "company_name", "type": "string", "required": True},
        {"name": "assessment_depth", "type": "enum", "choices": ["summary", "detailed"], "default": "detailed"},
        {"name": "include_compensation", "type": "boolean", "default": True},
        {"name": "include_board_governance", "type": "boolean", "default": True},
        {"name": "include_culture", "type": "boolean", "default": True},
        {"name": "focus_succession_risk", "type": "boolean", "default": True},
        {"name": "min_leadership_team_size", "type": "integer", "default": 3, "min": 1, "max": 20},
    ]
}

TEMPLATE = {
    "name": "Management Assessment",
    "domain": "private_equity",
    "category": "diligence",
    "description": "Comprehensive leadership team and organizational capability assessment",
    "prompt_template": MANAGEMENT_ASSESSMENT_PROMPT,
    "variables_schema": MANAGEMENT_ASSESSMENT_SCHEMA,
    "output_format": "json",
    "min_documents": 1,
    "max_documents": 10,
    "version": 1,
}
