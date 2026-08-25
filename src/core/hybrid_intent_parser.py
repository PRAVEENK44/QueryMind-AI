"""Hybrid Intent Parser - Rule-based with LLM fallback."""
from typing import Any

from src.core.intent_parser import IntentParser as RuleBasedParser
from src.llm.client import IntentParserLLM, get_llm_client


class IntentParser:
    """
    Hybrid intent parser combining rule-based and LLM approaches.
    
    Flow:
    1. Try rule-based parser first (fast, deterministic)
    2. If confidence is low or query is complex, use LLM
    3. Validate and return result
    """

    COMPLEX_QUERY_INDICATORS = [
        "compare",
        "vs",
        "versus",
        "difference between",
        "why",
        "how come",
        "what if",
        "analyze",
        "insight",
        "which one",
        "relationship",
        "correlation",
    ]

    def __init__(self, use_llm_fallback: bool = True):
        self.rule_based = RuleBasedParser()
        self.use_llm_fallback = use_llm_fallback
        self._llm_parser: IntentParserLLM | None = None

    @property
    def llm_parser(self) -> IntentParserLLM | None:
        """Lazy load LLM parser."""
        if self._llm_parser is None:
            client = get_llm_client()
            if client and client.api_key:
                self._llm_parser = IntentParserLLM(client)
        return self._llm_parser

    def parse(
        self,
        query: str,
        previous_intent: Any | None = None,
        schema_info: dict | None = None,
    ) -> Any:
        """
        Parse query with hybrid approach.
        
        Args:
            query: Natural language query
            previous_intent: Previous query intent for refinement
            schema_info: Database schema info (for LLM)
            
        Returns:
            QueryIntent object
        """
        # First, try rule-based parsing
        intent = self.rule_based.parse(query, previous_intent)

        # Check if we should use LLM fallback
        if self.use_llm_fallback and self._should_use_llm(query, intent):
            llm_intent = self._parse_with_llm(query, schema_info, previous_intent)
            if llm_intent:
                return self._convert_to_intent(llm_intent, intent)

        return intent

    def _should_use_llm(self, query: str, rule_intent: Any) -> bool:
        """Determine if query should use LLM fallback."""
        query_lower = query.lower()

        # Check for complex query patterns
        for indicator in self.COMPLEX_QUERY_INDICATORS:
            if indicator in query_lower:
                return True

        # Check if rule-based produced low-confidence result
        if not rule_intent.metric or rule_intent.metric == "amount":
            if any(word in query_lower for word in ["analyze", "insight", "understand"]):
                return True

        return False

    def _parse_with_llm(
        self,
        query: str,
        schema_info: dict | None,
        previous_intent: Any | None,
    ) -> dict | None:
        """Parse using LLM when rule-based fails."""
        if not self.llm_parser or not schema_info:
            return None

        prev_dict = None
        if previous_intent:
            prev_dict = {
                "metric": previous_intent.metric,
                "aggregation": previous_intent.aggregation,
                "group_by": previous_intent.group_by,
                "filters": {
                    "time_range": previous_intent.filters.time_range,
                    "city": previous_intent.filters.city,
                    "category": previous_intent.filters.category,
                },
            }

        try:
            return self.llm_parser.parse(query, schema_info, prev_dict)
        except Exception as e:
            print(f"LLM parsing failed: {e}")
            return None

    def _convert_to_intent(self, llm_intent: dict, fallback_intent: Any) -> Any:
        """Convert LLM intent to QueryIntent object."""
        from src.core.intent_parser import QueryFilters, QueryIntent

        filters = llm_intent.get("filters", {})

        return QueryIntent(
            metric=llm_intent.get("metric", fallback_intent.metric),
            aggregation=llm_intent.get("aggregation", fallback_intent.aggregation),
            group_by=llm_intent.get("group_by", fallback_intent.group_by),
            filters=QueryFilters(
                time_range=filters.get("time_range", fallback_intent.filters.time_range),
                city=filters.get("city", fallback_intent.filters.city),
                category=filters.get("category", fallback_intent.filters.category),
            ),
            limit=llm_intent.get("limit", fallback_intent.limit),
            chart=llm_intent.get("chart", fallback_intent.chart),
        )


def create_hybrid_parser(use_llm: bool = True) -> IntentParser:
    """Factory function to create hybrid parser."""
    return IntentParser(use_llm_fallback=use_llm)
