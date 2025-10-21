# backend/app/llm_client.py
import json
import logging
from anthropic import Anthropic
from typing import Dict

from app.config import settings

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

        if settings.mock_mode == True:
          logger.info("Mock mode: returning fake response")
          return {
            "company_info": {
                "company_name": "TestCo",
                "company_id": "123456",
                "industry": "Mock",
                "secondary_industry": None,
                "founded_year": 2020,
                "employees": 50,
                "headquarters": "Mock City",
                "business_structure": "LLC",
                "naics_codes": None,
                "sic_codes": None
            },
            "financials": {
                "currency": "USD",
                "fiscal_year_end": "12-31",
                "revenue_by_year": {},
                "ebitda_by_year": {},
                "adjusted_ebitda_by_year": {},
                "net_income_by_year": {},
                "gross_margin_by_year": {},
                "other_metrics": {}
            },
            "balance_sheet": {},
            "financial_ratios": {},
            "customers": {},
            "market": {},
            "key_risks": [],
            "investment_thesis": "Mock thesis",
            "management_team": [],
            "transaction_details": {}
        }
        
        prompt = self._create_prompt(text)
        
        logger.info(f"Calling Claude API with {len(prompt)} char prompt")
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
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
        text = response_text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        return json.loads(text)
    
    def _create_prompt(self, text: str) -> str:
        """Create the extraction prompt for Claude"""
        return f"""You are analyzing a Confidential Information Memorandum (CIM) or business document.

Extract comprehensive structured data. Return ONLY valid JSON.

{{
  "company_info": {{
    "company_name": "string or null",
    "company_id": "string or null",
    "industry": "string or null",
    "secondary_industry": "string or null",
    "founded_year": "number or null",
    "employees": "number or null",
    "headquarters": "string or null",
    "business_structure": "string or null",
    "naics_codes": "string or null",
    "sic_codes": "string or null"
  }},
  
  "financials": {{
    "currency": "string (USD, EUR, etc.)",
    "fiscal_year_end": "string or null",
    "revenue_by_year": {{
      // Extract ALL years (historical AND projected)
      // Format: "2014": 25302860, "2019_projected": 33029158
    }},
    "ebitda_by_year": {{}},
    "adjusted_ebitda_by_year": {{}},
    "net_income_by_year": {{}},
    "gross_margin_by_year": {{}},
    "other_metrics": {{
      "gross_margin_percent": "string or null",
      "ebitda_margin": "string or null",
      "net_margin": "string or null",
      "revenue_cagr": "string or null",
      "trailing_twelve_months_revenue": "number or null",
      "trailing_twelve_months_ebitda": "number or null"
    }}
  }},
  
  "balance_sheet": {{
    "most_recent_year": "number",
    "total_assets": "number or null",
    "current_assets": "number or null",
    "fixed_assets": "number or null",
    "total_liabilities": "number or null",
    "current_liabilities": "number or null",
    "long_term_debt": "number or null",
    "stockholders_equity": "number or null",
    "working_capital": "number or null"
  }},
  
  "financial_ratios": {{
    "current_ratio": "number or null",
    "quick_ratio": "number or null",
    "debt_to_equity": "number or null",
    "return_on_assets": "number or null",
    "return_on_equity": "number or null",
    "inventory_turnover": "number or null",
    "accounts_receivable_turnover": "number or null"
  }},
  
  "customers": {{
    "total_count": "number or null",
    "top_customer_concentration": "string or null",
    "customer_retention_rate": "string or null",
    "notable_customers": ["array of strings"]
  }},
  
  "market": {{
    "market_size": "string or null",
    "market_growth_rate": "string or null",
    "competitive_position": "string or null",
    "market_share": "string or null"
  }},
  
  "key_risks": [
    {{
      "risk": "string",
      "severity": "High/Medium/Low",
      "description": "string"
    }}
  ],
  
  "investment_thesis": "string or null",
  
  "management_team": [
    {{
      "name": "string",
      "title": "string",
      "background": "string or null"
    }}
  ],
  
  "transaction_details": {{
    "seller_motivation": "string or null",
    "post_sale_involvement": "string or null",
    "auction_deadline": "string or null",
    "assets_for_sale": "string or null"
  }}
}}

SPECIAL INSTRUCTIONS:
1. Extract ALL years of financial data found (historical AND projected)
2. For key_risks: Look for explicit "Key Risks" sections AND infer from:
   - Financial ratios (high debt, low liquidity, declining margins)
   - Business factors (customer concentration, competition, market risks)
   - Transaction factors (auction process, seller dependency)
   - Operational risks mentioned anywhere in document
3. For management_team: Look for "Management", "Leadership", "Key Personnel" sections
4. For customers: Extract concentration percentages and notable customer names
5. Use null for missing data - NEVER invent numbers
6. Return ONLY valid JSON with no markdown formatting

Document text:
{text}

Return ONLY the JSON object."""