"""
Query Analyzer for RAG

Analyzes user queries to determine intent and provide intelligent boosting hints
for hybrid search ranking.
"""

from typing import Dict, Set
import re
import logging

logger = logging.getLogger(__name__)


class QueryAnalyzer:
    """
    Analyzes user queries to determine preferences for content types

    Provides query-adaptive boosting hints:
    - Table/data queries get table boost
    - Narrative queries get narrative boost
    - Generic queries get neutral boost
    """

    # Keywords indicating preference for tables/structured data
    TABLE_KEYWORDS: Set[str] = {
        # Numbers & metrics
        "number", "numbers", "data", "table", "statistics", "stats",
        "percentage", "percent", "rate", "ratio", "value", "values",

        # Financial terms
        "revenue", "cost", "profit", "loss", "earnings", "income",
        "expense", "expenses", "price", "prices", "amount", "total",
        "growth", "decline", "margin", "ebitda", "cash flow",

        # Comparisons & aggregations
        "comparison", "compare", "breakdown", "distribution",
        "average", "mean", "median", "sum", "count", "maximum", "minimum",

        # Structured content
        "list", "listing", "chart", "graph", "figure", "exhibit",
        "summary table", "schedule", "statement"
    }

    # Keywords indicating preference for narrative content
    NARRATIVE_KEYWORDS: Set[str] = {
        # Explanatory
        "explain", "describe", "why", "how", "reason", "background",
        "overview", "summary", "story", "context", "detail", "details",
        "analysis", "discussion", "commentary",

        # Qualitative
        "strategy", "approach", "plan", "vision", "mission",
        "opportunity", "challenge", "risk", "threat",
        "strength", "weakness", "competitive advantage",

        # Process & causation
        "process", "procedure", "methodology", "because", "since",
        "therefore", "consequently", "impact", "effect", "influence"
    }

    def __init__(self):
        """Initialize query analyzer"""
        self.table_keywords = self.TABLE_KEYWORDS
        self.narrative_keywords = self.NARRATIVE_KEYWORDS

    def analyze(self, query: str) -> Dict:
        """
        Analyze query to determine content preferences

        Args:
            query: User's search query

        Returns:
            Dictionary with analysis results:
            {
                "prefer_tables": bool,
                "prefer_narrative": bool,
                "table_boost": float,
                "narrative_boost": float,
                "query_type": str,
                "matched_keywords": List[str]
            }
        """
        query_lower = query.lower()
        words = set(query_lower.split())

        # Check for table/data indicators
        table_matches = words & self.table_keywords
        has_numbers = bool(re.search(r'\d+', query))  # Contains numbers

        # Check for narrative indicators
        narrative_matches = words & self.narrative_keywords

        # Check for question words (often narrative)
        question_words = {"what", "why", "how", "when", "where", "who"}
        has_question_word = bool(words & question_words)

        # Determine preference based on matches
        table_score = len(table_matches) + (1 if has_numbers else 0)
        narrative_score = len(narrative_matches) + (1 if has_question_word else 0)

        # Decision logic
        # Key principle:
        # - Data queries: boost tables, penalize narrative (user wants numbers, not fluff)
        # - Narrative queries: boost narrative, keep tables neutral (tables can support narrative)
        # - Generic queries: neutral for both

        if table_score > narrative_score and table_score > 0:
            # Data query: user wants numbers/metrics
            prefer_tables = True
            prefer_narrative = False
            table_boost = 1.2  # 20% boost for tables (has the data)
            narrative_boost = 0.9  # 10% penalty for narrative (might be verbose/fluff)
            query_type = "data_query"
        elif narrative_score > table_score and narrative_score > 0:
            # Narrative query: user wants explanations/context
            prefer_tables = False
            prefer_narrative = True
            table_boost = 1.0  # Neutral for tables (can provide supporting evidence)
            narrative_boost = 1.1  # 10% boost for narrative (has explanations)
            query_type = "narrative_query"
        else:
            # Neutral: no clear preference
            prefer_tables = False
            prefer_narrative = False
            table_boost = 1.0
            narrative_boost = 1.0
            query_type = "generic_query"

        result = {
            "prefer_tables": prefer_tables,
            "prefer_narrative": prefer_narrative,
            "table_boost": table_boost,
            "narrative_boost": narrative_boost,
            "query_type": query_type,
            "matched_table_keywords": list(table_matches),
            "matched_narrative_keywords": list(narrative_matches),
            "has_numbers": has_numbers,
            "has_question_word": has_question_word
        }

        logger.debug(
            f"Query analysis: type={query_type}, "
            f"table_boost={table_boost}, narrative_boost={narrative_boost}",
            extra={"query": query[:50], "analysis": result}
        )

        return result

    def add_table_keyword(self, keyword: str) -> None:
        """Add custom table keyword (for domain-specific terms)"""
        self.table_keywords.add(keyword.lower())

    def add_narrative_keyword(self, keyword: str) -> None:
        """Add custom narrative keyword (for domain-specific terms)"""
        self.narrative_keywords.add(keyword.lower())

    def add_domain_keywords(self, table_keywords: Set[str] = None, narrative_keywords: Set[str] = None) -> None:
        """
        Add domain-specific keywords in bulk

        Args:
            table_keywords: Set of keywords indicating table/data preference
            narrative_keywords: Set of keywords indicating narrative preference
        """
        if table_keywords:
            self.table_keywords.update(k.lower() for k in table_keywords)
        if narrative_keywords:
            self.narrative_keywords.update(k.lower() for k in narrative_keywords)