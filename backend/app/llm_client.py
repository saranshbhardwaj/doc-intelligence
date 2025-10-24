# backend/app/llm_client.py
from datetime import datetime
import json
import logging
import uuid
from anthropic import Anthropic
from typing import Dict

from app.config import settings
from services.extraction_prompt import SYSTEM_PROMPT, create_extraction_prompt

logger = logging.getLogger(__name__)

class LLMClient:
    """Handle Claude API interactions"""
    
    def __init__(self, api_key: str, model: str, max_tokens: int, max_input_chars: int):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.max_input_chars = max_input_chars
    
    def extract_structured_data(self, text: str) -> Dict:
        """
        Send text to Claude and get structured JSON back.
        Raises HTTPException if API call fails.
        """
        # Truncate text if too long
        if len(text) > self.max_input_chars:
            logger.warning(f"Text truncated from {len(text)} to {self.max_input_chars} chars")
            text = text[:self.max_input_chars]

        # if settings.mock_mode == True:
        #   logger.info("Mock mode: returning fake response")
        #   return self.get_mock_response()
        
        prompt = self._create_prompt(text)
        
        logger.info(f"Calling Claude API with {len(prompt)} char prompt")
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract text from response
            response_text = message.content[0].text.strip()
            
            logger.info(f"Claude response: {len(response_text)} chars")
            
            # Parse JSON from response
            parsed_json = self._parse_json_response(response_text)
            
            return parsed_json
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.error(f"Raw response: {response_text[:500]}...")
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail="The AI returned invalid data format. Please try again or contact support."
            )
        except Exception as e:
            logger.exception(f"Claude API error: {e}")
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail="AI service temporarily unavailable. Please try again in a moment."
            )
    
    def _parse_json_response(self, response_text: str) -> Dict:
        """Extract and parse JSON from Claude's response"""
        # Remove markdown code blocks if present
        text = response_text.strip()

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1].strip()
        # Remove any leading/trailing whitespace
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error at position {e.pos}: {e.msg}")
            logger.error(f"Context around error: ...{text[max(0, e.pos-100):e.pos+100]}...")
            
            # Try to fix common issues
            text = self._fix_common_json_errors(text)
            
            try:
                return json.loads(text)
            except json.JSONDecodeError as e2:
                logger.error(f"Still failed after fixes: {e2}")
                raise
    
    def _fix_common_json_errors(self, text: str) -> str:
        """Attempt to fix common JSON formatting issues"""
        import re
        
        # Fix trailing commas before closing braces/brackets
        text = re.sub(r',(\s*[}\]])', r'\1', text)
        
        # Fix missing commas between properties (common Claude error)
        # This is risky but can help: "value1"\n  "key2" -> "value1",\n  "key2"
        text = re.sub(r'"\s*\n\s*"', '",\n  "', text)
        
        # Fix truncated strings (if response was cut off)
        # Find unclosed quotes at the end
        if text.count('"') % 2 != 0:
            # Odd number of quotes - add closing quote
            last_quote = text.rfind('"')
            if last_quote > len(text) - 50:  # If near the end
                text = text[:last_quote+1] + '"' + text[last_quote+1:]
        
        return text
    
    def _create_prompt(self, text: str) -> str:
      """Create extraction prompt using the new comprehensive format"""
      return create_extraction_prompt(text)
    
    def get_mock_response(self) -> Dict:
        """Enhanced mock response matching exact Pydantic models"""
        return {
            "data": {
                "company_info": {
                    "company_name": "TechFlow Solutions Inc.",
                    "company_id": "Project Thunder",
                    "industry": "Software & Technology",
                    "secondary_industry": "SaaS",
                    "business_structure": "C-Corporation",
                    "founded_year": 2015,
                    "employees": 250,
                    "headquarters": "Austin, TX",
                    "website": "www.techflowsolutions.com",
                    "naics_codes": "511210, 518210",
                    "sic_codes": "7372, 7371",
                    "provenance": {
                        "section_heading": "Company Overview",
                        "page_numbers": [1, 2],
                        "text_excerpt": "TechFlow Solutions is a leading enterprise SaaS provider..."
                    },
                    "confidence": 0.95
                },
                "financials": {
                    "currency": "USD",
                    "fiscal_year_end": "December 31",
                    "revenue_by_year": {
                        "2021": 15000000.0,
                        "2022": 22000000.0,
                        "2023": 32000000.0,
                        "projected_2024": 45000000.0,
                        "projected_2025": 60000000.0
                    },
                    "ebitda_by_year": {
                        "2021": 3000000.0,
                        "2022": 5500000.0,
                        "2023": 9600000.0,
                        "projected_2024": 14000000.0
                    },
                    "adjusted_ebitda_by_year": {
                        "2021": 3500000.0,
                        "2022": 6200000.0,
                        "2023": 10500000.0,
                        "projected_2024": 15000000.0
                    },
                    "net_income_by_year": {
                        "2021": 2000000.0,
                        "2022": 3800000.0,
                        "2023": 6500000.0
                    },
                    "gross_margin_by_year": {
                        "2021": 0.72,
                        "2022": 0.75,
                        "2023": 0.78
                    },
                    "other_metrics": {
                        "assumptions": "All figures in USD",
                        "d_and_a": 1500000.0
                    },
                    "provenance": {
                        "section_heading": "Financial Performance",
                        "page_numbers": [10, 11, 12],
                        "text_excerpt": "Historical revenue growth of 46% CAGR from 2021-2023..."
                    },
                    "confidence": 0.9
                },
                "balance_sheet": {
                    "most_recent_year": 2023,
                    "total_assets": 45000000.0,
                    "current_assets": 25000000.0,
                    "fixed_assets": 20000000.0,
                    "total_liabilities": 15000000.0,
                    "current_liabilities": 8000000.0,
                    "long_term_debt": 7000000.0,
                    "stockholders_equity": 30000000.0,
                    "working_capital": 17000000.0,
                    "provenance": {
                        "section_heading": "Balance Sheet",
                        "page_numbers": [15],
                        "text_excerpt": "As of December 31, 2023, total assets of $45M..."
                    },
                    "confidence": 0.9
                },
                "financial_ratios": {
                    "current_ratio": 3.125,
                    "quick_ratio": 2.8,
                    "debt_to_equity": 0.233,
                    "return_on_assets": 0.144,
                    "return_on_equity": 0.217,
                    "inventory_turnover": 12.5,
                    "accounts_receivable_turnover": 8.2,
                    "ebitda_margin": 0.30,
                    "capex_pct_revenue": 0.08,
                    "net_debt_to_ebitda": 0.5,
                    "provenance": {
                        "section_heading": "Financial Ratios",
                        "page_numbers": [16],
                        "text_excerpt": "Strong liquidity with current ratio of 3.1x..."
                    },
                    "confidence": 0.9
                },
                "customers": {
                    "total_count": 450,
                    "top_customer_concentration": "Top 10 customers",
                    "top_customer_concentration_pct": 0.35,
                    "customer_retention_rate": "95%",
                    "notable_customers": ["Fortune 500 Tech Co", "Global Bank Corp", "Healthcare Systems Inc"],
                    "recurring_revenue_pct": 0.85,
                    "revenue_mix_by_segment": {
                        "Enterprise": 0.60,
                        "Mid-Market": 0.30,
                        "SMB": 0.10
                    },
                    "provenance": {
                        "section_heading": "Customer Base",
                        "page_numbers": [20, 21],
                        "text_excerpt": "450 customers across enterprise and mid-market segments..."
                    },
                    "confidence": 0.85
                },
                "market": {
                    "market_size": "$5B Total Addressable Market",
                    "market_size_estimate": 5000000000.0,
                    "market_growth_rate": "25% CAGR through 2028",
                    "competitive_position": "Top 3 player in mid-market segment",
                    "market_share": "~5% of addressable market",
                    "provenance": {
                        "section_heading": "Market Analysis",
                        "page_numbers": [25, 26],
                        "text_excerpt": "Serving a $5B TAM growing at 25% annually..."
                    },
                    "confidence": 0.75
                },
                "key_risks": [
                    {
                        "risk": "Customer Concentration Risk",
                        "severity": "High",
                        "description": "Top 10 customers represent 35% of revenue. Loss of major accounts could impact performance.",
                        "inferred": False,
                        "mitigation": "Active diversification with 50+ deals in pipeline. Customer success programs to reduce churn.",
                        "provenance": {
                            "section_heading": "Risk Factors",
                            "page_numbers": [40],
                            "text_excerpt": "Customer concentration presents risk with top 10 at 35%..."
                        },
                        "confidence": 0.9
                    },
                    {
                        "risk": "Competitive Pressure",
                        "severity": "High",
                        "description": "Well-funded startups and large incumbents entering market.",
                        "inferred": False,
                        "mitigation": "Strong product differentiation and high switching costs (18-month implementations).",
                        "provenance": {
                            "section_heading": "Competitive Landscape",
                            "page_numbers": [28],
                            "text_excerpt": "Competition intensifying from funded startups..."
                        },
                        "confidence": 0.85
                    },
                    {
                        "risk": "Key Person Dependency",
                        "severity": "Medium",
                        "description": "Heavy reliance on founder for customer relationships and product vision.",
                        "inferred": True,
                        "mitigation": "12-month transition period with knowledge transfer. Building professional management team.",
                        "provenance": {
                            "section_heading": "Management Team",
                            "page_numbers": [35],
                            "text_excerpt": "Founder has been instrumental in company growth..."
                        },
                        "confidence": 0.75
                    }
                ],
                "management_team": [
                    {
                        "name": "John Smith",
                        "title": "Founder & CEO",
                        "background": "15+ years in enterprise software. Previously VP at Salesforce. Stanford CS and Wharton MBA.",
                        "linkedin": "https://linkedin.com/in/johnsmith",
                        "provenance": {
                            "section_heading": "Management Biographies",
                            "page_numbers": [35],
                            "text_excerpt": "John Smith founded TechFlow in 2015..."
                        },
                        "confidence": 0.95
                    },
                    {
                        "name": "Sarah Johnson",
                        "title": "CFO",
                        "background": "Former Big 4 partner with 20 years in tech M&A. Led 5 PE-backed exits.",
                        "linkedin": "https://linkedin.com/in/sarahjohnson",
                        "provenance": {
                            "section_heading": "Management Biographies",
                            "page_numbers": [36],
                            "text_excerpt": "Sarah joined as CFO in 2021..."
                        },
                        "confidence": 0.95
                    },
                    {
                        "name": "Michael Chen",
                        "title": "CTO",
                        "background": "Ex-Google engineer. PhD in CS from Berkeley. 10 patents in AI/ML.",
                        "linkedin": "https://linkedin.com/in/michaelchen",
                        "provenance": {
                            "section_heading": "Management Biographies",
                            "page_numbers": [36],
                            "text_excerpt": "Michael leads product and engineering..."
                        },
                        "confidence": 0.95
                    }
                ],
                "transaction_details": {
                    "seller_motivation": "Founder seeking liquidity after 10 years to pursue new ventures.",
                    "post_sale_involvement": "Founder willing to stay as advisor for 12 months. CTO on 3-year earnout.",
                    "auction_deadline": "Q1 2025",
                    "assets_for_sale": "100% equity stake in operating company",
                    "deal_type": "majority",
                    "asking_price": 150000000.0,
                    "implied_valuation_hint": "~4.7x 2023 Revenue, ~14.3x 2023 Adj. EBITDA",
                    "provenance": {
                        "section_heading": "Transaction Overview",
                        "page_numbers": [3, 4],
                        "text_excerpt": "Seeking strategic partner at $150M valuation..."
                    },
                    "confidence": 0.9
                },
                "growth_analysis": {
                    "historical_cagr": 0.46,
                    "projected_cagr": 0.37,
                    "organic_pct": 0.92,
                    "m_and_a_pct": 0.08,
                    "organic_growth_estimate": "Strong product-market fit driving 15% annual growth in existing customers. New product lines contributing 10%. Enterprise expansion adding 21% YoY.",
                    "m_and_a_summary": "DataSync acquisition in Q2 2023 for $5M added $1.5M ARR and analytics capabilities. Represents 8% of 2023 growth.",
                    "notes": "2024 projections assume continued momentum plus two planned add-ons totaling $8M.",
                    "provenance": {
                        "section_heading": "Growth Strategy",
                        "page_numbers": [18, 19],
                        "text_excerpt": "Historical 46% CAGR driven primarily by organic expansion..."
                    },
                    "confidence": 0.85
                },
                "valuation_multiples": {
                    "asking_ev_ebitda": 14.3,
                    "asking_ev_revenue": 4.7,
                    "asking_price_ebitda": 14.3,
                    "exit_ev_ebitda_estimate": 12.0,
                    "comparable_multiples_range": "10-16x EBITDA for high-growth SaaS",
                    "provenance": {
                        "section_heading": "Valuation Framework",
                        "page_numbers": [5],
                        "text_excerpt": "Asking price of $150M implies 14.3x 2023 Adj. EBITDA..."
                    },
                    "confidence": 0.9
                },
                "capital_structure": {
                    "existing_debt": 7000000.0,
                    "debt_to_ebitda": 0.67,
                    "proposed_leverage": 5.0,
                    "equity_contribution_estimate": 120000000.0,
                    "provenance": {
                        "section_heading": "Capitalization",
                        "page_numbers": [15],
                        "text_excerpt": "Current debt of $7M at 0.67x EBITDA. Transaction assumes 5x leverage..."
                    },
                    "confidence": 0.85
                },
                "operating_metrics": {
                    "capex_by_year": {
                        "2021": 1200000.0,
                        "2022": 1800000.0,
                        "2023": 2500000.0,
                        "projected_2024": 3600000.0
                    },
                    "fcf_by_year": {
                        "2021": 3900000.0,
                        "2022": 6800000.0,
                        "2023": 11200000.0,
                        "projected_2024": 16500000.0
                    },
                    "working_capital_pct_revenue": 0.05,
                    "pricing_power": "High",
                    "contract_structure": "Annual contracts with 10-20% price increases. 85% under multi-year agreements with auto-renewal.",
                    "provenance": {
                        "section_heading": "Business Model",
                        "page_numbers": [22, 23],
                        "text_excerpt": "Strong pricing power with consistent increases and minimal churn..."
                    },
                    "confidence": 0.8
                },
                "strategic_rationale": {
                    "deal_thesis": "Compelling platform investment with 46% CAGR and strong unit economics. Market leader in underpenetrated $5B vertical with clear path to $100M+ revenue.",
                    "value_creation_plan": "Sales acceleration, international expansion (UK/EU), 3-5 strategic tuck-ins, operational improvements in R&D efficiency.",
                    "add_on_opportunities": "Fragmented market with 200+ targets ($1M-$10M revenue). Pipeline of 8 near-term targets adding complementary capabilities.",
                    "competitive_advantages": [
                        "Market-leading product with NPS of 72",
                        "Proprietary AI/ML with patent protection",
                        "High switching costs (18-month implementations)",
                        "Strong brand with 95% aided awareness",
                        "Vertical expertise that generalists cannot replicate"
                    ],
                    "key_risks_summary": "Primary risks: customer concentration (35%), competitive pressure, key person dependency, international execution risk.",
                    "provenance": {
                        "section_heading": "Investment Highlights",
                        "page_numbers": [6, 7, 8],
                        "text_excerpt": "TechFlow represents compelling platform with multiple value creation levers..."
                    },
                    "confidence": 0.85
                },
                "investment_thesis": "TechFlow Solutions represents a compelling investment opportunity in the high-growth enterprise SaaS market. The company has demonstrated exceptional revenue growth (46% CAGR) with strong unit economics and improving margins.\n\nKey investment highlights:\n• Market Leader: Top 3 player in $5B TAM growing 25% annually\n• Strong Financials: 85% recurring revenue, 95% retention, 30% EBITDA margins\n• Scalable Platform: Fortune 500 customers with high NPS\n• Growth Runway: Enterprise whitespace plus international expansion\n• Experienced Management: Deep expertise with proven execution",
                "derived_metrics": {
                    "ttm_revenue": 32000000.0,
                    "revenue_per_employee": 128000.0,
                    "ebitda_per_employee": 38400.0,
                    "rule_of_40": 76.0,
                    "ltv_cac_ratio": 4.2,
                    "payback_period_months": 14
                },
                "raw_sections": None,
                "field_confidence": None,
                "field_provenance": None,
                "extraction_notes": "Mock data for UI testing. All figures are fabricated examples."
            },
            "metadata": {
                "request_id": "mock-test-" + str(uuid.uuid4())[:8],
                "filename": "TechFlow_CIM_2024.pdf",
                "file_label": "TechFlow Solutions - Project Thunder",
                "pages": 55,
                "characters_extracted": 125000,
                "processing_time_seconds": 2.5,
                "timestamp": datetime.now(datetime.timezone.utc),
                "is_scanned_pdf": False,
                "ocr_used": False
            }
        }
