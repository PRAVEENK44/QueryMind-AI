"""Query Suggestions - Suggest follow-up queries to users."""
from typing import Any


class QuerySuggester:
    """
    Generate contextual query suggestions after results are shown.
    
    Suggests based on:
    - Current query type
    - Available filters
    - Common patterns
    """

    def __init__(self):
        self.suggestion_templates = self._build_templates()

    def _build_templates(self) -> dict[str, list[dict]]:
        """Build suggestion templates by query type."""
        return {
            "revenue": [
                {"query": "Show revenue by city", "label": "Breakdown by city"},
                {"query": "Show monthly revenue trend", "label": "Monthly trend"},
                {"query": "Filter by Bangalore", "label": "Just Bangalore"},
                {"query": "Show top products by revenue", "label": "Top products"},
            ],
            "products": [
                {"query": "Show top 5 products by revenue", "label": "Top 5"},
                {"query": "Show category-wise distribution", "label": "By category"},
                {"query": "Show revenue by product", "label": "Product revenue"},
            ],
            "city": [
                {"query": "Show revenue by city", "label": "Revenue by city"},
                {"query": "Filter by Delhi", "label": "Just Delhi"},
                {"query": "Compare top cities", "label": "Compare cities"},
            ],
            "category": [
                {"query": "Show category distribution", "label": "Distribution"},
                {"query": "Show sales by category", "label": "Sales by category"},
                {"query": "Filter by Electronics", "label": "Just Electronics"},
            ],
            "time": [
                {"query": "Show last 3 months trend", "label": "Last 3 months"},
                {"query": "Show last year comparison", "label": "Last year"},
                {"query": "Show monthly breakdown", "label": "Monthly view"},
            ],
            "default": [
                {"query": "Show revenue by city", "label": "By city"},
                {"query": "Show monthly trend", "label": "Trend"},
                {"query": "Show top 5 products", "label": "Top products"},
            ],
        }

    def suggest(
        self,
        query: str,
        intent: dict[str, Any],
        result: Any,
    ) -> list[dict[str, str]]:
        """
        Generate suggestions based on current query.
        
        Args:
            query: Original user query
            intent: Parsed query intent
            result: Query execution result
            
        Returns:
            List of suggestions with query text and label
        """
        query_lower = query.lower()
        suggestions = []

        # Determine query type
        query_type = self._detect_query_type(query_lower, intent)

        # Get templates for this type
        templates = self.suggestion_templates.get(query_type, self.suggestion_templates["default"])

        # Add relevant suggestions
        for template in templates[:4]:
            # Skip if too similar to current query
            if self._is_similar(template["query"], query_lower):
                continue
            suggestions.append(template)

        # Add contextual suggestions based on filters
        contextual = self._get_contextual_suggestions(intent)
        suggestions.extend(contextual)

        # Return unique suggestions
        seen = set()
        unique = []
        for s in suggestions:
            key = s["query"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique[:5]

    def _detect_query_type(self, query: str, intent: dict) -> str:
        """Detect the primary type of query."""
        if any(w in query for w in ["revenue", "sales", "amount", "income"]):
            return "revenue"
        if any(w in query for w in ["product", "item"]):
            return "products"
        if "city" in query or "location" in query:
            return "city"
        if "category" in query:
            return "category"
        if any(w in query for w in ["month", "trend", "time", "year", "date"]):
            return "time"

        # Check intent
        metric = intent.get("metric", "")
        if metric in ["amount", "revenue"]:
            return "revenue"
        if metric in ["product_id", "name"]:
            return "products"

        return "default"

    def _is_similar(self, suggestion: str, query: str) -> bool:
        """Check if suggestion is too similar to current query."""
        # Extract key words
        suggestion_words = set(suggestion.lower().split())
        query_words = set(query.split())

        # Check overlap
        overlap = suggestion_words & query_words

        # If more than 50% words overlap, skip
        return len(overlap) > len(suggestion_words) * 0.5

    def _get_contextual_suggestions(self, intent: dict) -> list[dict]:
        """Get contextual suggestions based on current filters."""
        suggestions = []
        filters = intent.get("filters", {})

        # If no city filter, suggest adding one
        if not filters.get("city"):
            suggestions.append({
                "query": "Filter by Bangalore",
                "label": "Add Bangalore filter",
            })

        # If no time filter, suggest adding one
        if not filters.get("time_range"):
            suggestions.append({
                "query": "Show last 6 months",
                "label": "Add time filter",
            })

        # If no group_by, suggest adding one
        if not intent.get("group_by"):
            suggestions.append({
                "query": "Group by category",
                "label": "Add grouping",
            })

        return suggestions


class SmartSuggester:
    """
    LLM-enhanced suggestion generator for more intelligent suggestions.
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.base_suggester = QuerySuggester()

    def suggest(
        self,
        query: str,
        intent: dict[str, Any],
        result: Any,
    ) -> list[dict[str, str]]:
        """Generate suggestions with LLM enhancement."""
        # Always get base suggestions
        suggestions = self.base_suggester.suggest(query, intent, result)

        # Try to enhance with LLM if available
        if self.llm and self.llm.api_key:
            try:
                llm_suggestions = self._get_llm_suggestions(query, intent, result)
                if llm_suggestions:
                    suggestions = llm_suggestions + suggestions[:2]
            except Exception:
                pass

        return suggestions[:5]

    def _get_llm_suggestions(
        self,
        query: str,
        intent: dict,
        result: Any,
    ) -> list[dict] | None:
        """Get LLM-powered suggestions."""
        # This would use the LLM to generate contextual suggestions
        # For now, return None to use base suggestions
        return None


def create_suggester() -> QuerySuggester:
    """Factory to create query suggester."""
    return QuerySuggester()


def create_smart_suggester(llm_client=None) -> SmartSuggester:
    """Factory to create smart suggester."""
    return SmartSuggester(llm_client)
