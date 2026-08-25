"""Enhanced Query Refinement - Better multi-turn memory."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryMemory:
    """
    Memory store for query context and refinement.
    
    Handles multi-turn conversations with intelligent merge.
    """
    last_query: str | None = None
    last_intent: dict[str, Any] | None = None
    last_sql: str | None = None
    last_result: dict[str, Any] | None = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)

    MAX_HISTORY = 10

    def update(self, query: str, intent: dict, sql: str, result: dict):
        """Update memory with new query."""
        self.last_query = query
        self.last_intent = intent
        self.last_sql = sql
        self.last_result = result

        # Add to history
        self.conversation_history.append({
            "query": query,
            "intent": intent,
            "sql": sql,
        })

        # Trim history
        if len(self.conversation_history) > self.MAX_HISTORY:
            self.conversation_history = self.conversation_history[-self.MAX_HISTORY:]

    def is_refinement(self, query: str) -> bool:
        """Check if query is a refinement of previous."""
        query_lower = query.lower()
        refinement_patterns = [
            "only", "just", "now", "add", "filter", "restrict",
            "with", "include", "exclude", "change", "update",
            "instead", "rather", "but", "however",
        ]

        # Also check if it's a short query (likely refinement)
        if len(query.split()) <= 5:
            return True

        return any(pattern in query_lower for pattern in refinement_patterns)

    def get_previous_intent(self) -> dict[str, Any] | None:
        """Get previous intent for refinement."""
        return self.last_intent


class QueryRefiner:
    """
    Intelligent query refinement with context understanding.
    
    Handles vague follow-ups and merges intelligently with previous query.
    """

    # Keywords that indicate refinement types
    FILTER_KEYWORDS = {
        "city": ["bangalore", "mumbai", "delhi", "chennai", "hyderabad", "kolkata", "pune"],
        "category": ["electronics", "clothing", "home", "sports", "books", "toys", "food"],
        "time_range": ["last week", "last month", "last 3 months", "last 6 months", "last year"],
    }

    MODIFIER_KEYWORDS = {
        "higher": {"aggregation": "max", "compare": "highest"},
        "lower": {"aggregation": "min", "compare": "lowest"},
        "average": {"aggregation": "avg"},
        "total": {"aggregation": "sum"},
        "count": {"aggregation": "count"},
        "top": {"order": "desc"},
        "bottom": {"order": "asc"},
    }

    def refine(
        self,
        query: str,
        previous_intent: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Refine previous intent with new query.
        
        Returns updated intent dictionary.
        """
        query_lower = query.lower()

        # Start with copy of previous intent
        refined = {
            "metric": previous_intent.get("metric", "amount"),
            "aggregation": previous_intent.get("aggregation", "sum"),
            "group_by": previous_intent.get("group_by"),
            "filters": dict(previous_intent.get("filters", {})),
            "limit": previous_intent.get("limit", 10),
            "chart": previous_intent.get("chart", "auto"),
        }

        # Apply filter changes
        refined["filters"] = self._apply_filters(query_lower, refined["filters"])

        # Apply modifier changes
        refined = self._apply_modifiers(query_lower, refined)

        # Apply limit changes
        refined["limit"] = self._apply_limit_changes(query, refined["limit"])

        # Apply chart changes
        refined["chart"] = self._apply_chart_changes(query_lower, refined["chart"])

        # Handle group_by changes
        refined["group_by"] = self._apply_group_changes(query_lower, refined["group_by"])

        return refined

    def _apply_filters(self, query: str, current_filters: dict) -> dict:
        """Apply filter changes from query."""
        filters = dict(current_filters)

        # Check for city filters
        for city in self.FILTER_KEYWORDS["city"]:
            if city in query:
                filters["city"] = city.title()

        # Check for category filters
        for cat in self.FILTER_KEYWORDS["category"]:
            if cat in query:
                filters["category"] = cat.title() if cat != "home" else "Home & Garden"

        # Check for time range
        for tr in self.FILTER_KEYWORDS["time_range"]:
            if tr in query:
                filters["time_range"] = tr.replace(" ", "_")

        return filters

    def _apply_modifiers(self, query: str, refined: dict) -> dict:
        """Apply aggregation/order modifiers."""
        for keyword, changes in self.MODIFIER_KEYWORDS.items():
            if keyword in query:
                if "aggregation" in changes:
                    refined["aggregation"] = changes["aggregation"]
                if "order" in changes:
                    refined["order"] = changes["order"]

        return refined

    def _apply_limit_changes(self, query: str, current_limit: int) -> int:
        """Apply limit changes."""
        import re
        match = re.search(r"(top|first|last|bottom)\s+(\d+)", query.lower())
        if match:
            return int(match.group(2))

        # Check for "only" followed by number
        match = re.search(r"only\s+(\d+)", query.lower())
        if match:
            return int(match.group(1))

        return current_limit

    def _apply_chart_changes(self, query: str, current_chart: str) -> str:
        """Apply chart type changes."""
        if "line chart" in query or "trend" in query:
            return "line"
        if "bar chart" in query:
            return "bar"
        if "pie chart" in query or "distribution" in query:
            return "pie"
        if "table" in query:
            return "table"
        return current_chart

    def _apply_group_changes(self, query: str, current_group: str | None) -> str | None:
        """Apply group_by changes."""
        if "by city" in query:
            return "city"
        if "by category" in query:
            return "category"
        if "by product" in query:
            return "name"
        if "monthly" in query or "trend" in query:
            return "date"
        return current_group


def create_query_memory() -> QueryMemory:
    """Factory to create query memory."""
    return QueryMemory()


def create_query_refiner() -> QueryRefiner:
    """Factory to create query refiner."""
    return QueryRefiner()
