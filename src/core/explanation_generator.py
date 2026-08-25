"""Explanation Generator - Generates natural language explanations (Lite Edition)."""
from typing import Any


class ExplanationGenerator:
    """Generates explanations for query results using native Python structures."""

    def generate(self, intent: dict[str, Any], sql_query: str,
                result_data: list[dict[str, Any]], is_refinement: bool = False) -> str:
        """
        Generate explanation for query and results.
        
        Args:
            intent: Query intent dictionary
            sql_query: Generated SQL query
            result_data: Query results as a list of dictionaries
            is_refinement: Whether this is a refined query
            
        Returns:
            Natural language explanation
        """
        parts = []

        # Start with what the query does
        query_explanation = self._explain_query(intent, is_refinement)
        parts.append(query_explanation)

        # Add what the results show
        if result_data:
            results_explanation = self._explain_results(intent, result_data)
            parts.append(results_explanation)
        else:
            parts.append("No results match your criteria. Try adjusting your filters.")

        # Add chart explanation
        chart_explanation = self._explain_chart(intent)
        parts.append(chart_explanation)

        return "\n\n".join(parts)

    def _explain_query(self, intent: dict[str, Any], is_refinement: bool) -> str:
        """Explain what the query does."""
        metric = intent.get("metric", "data")
        agg = intent.get("aggregation", "count")
        group_by = intent.get("group_by")

        explanation = "This query shows "

        if is_refinement:
            explanation = "This refined query shows "

        # Aggregation
        if agg == "count":
            explanation += "the count of "
        elif agg == "sum":
            explanation += "the total "
        elif agg == "avg":
            explanation += "the average "
        elif agg == "max":
            explanation += "the maximum "
        elif agg == "min":
            explanation += "the minimum "

        # Metric
        if metric == "amount":
            explanation += "revenue"
        else:
            explanation += str(metric)

        # Grouping
        if group_by:
            if group_by == "date":
                explanation += " over time (monthly)"
            elif group_by == "name":
                explanation += " by product"
            elif group_by == "category":
                explanation += " by category"
            elif group_by == "city":
                explanation += " by city"

        # Filters
        filters = intent.get("filters", {})
        if isinstance(filters, object) and hasattr(filters, "dict"):
            filters = filters.dict() # Handle Pydantic model

        filter_parts = []
        if filters.get("city"):
            filter_parts.append(f"orders from {filters['city']}")
        if filters.get("category"):
            filter_parts.append(f"products in {filters['category']}")
        if filters.get("time_range"):
            filter_parts.append(f"in the {str(filters['time_range']).replace('_', ' ')}")

        if filter_parts:
            explanation += ", filtered by " + ", ".join(filter_parts)

        explanation += "."

        return explanation

    def _explain_results(self, intent: dict[str, Any], result_data: list[dict[str, Any]]) -> str:
        """Explain what the results show using native list processing."""
        if not result_data:
            return "No results match your criteria."

        row_count = len(result_data)
        columns = list(result_data[0].keys())

        # Get the metric column
        metric_col = None
        for col in ["amount", "revenue", "value", "total", "count", "order_count"]:
            if col in columns:
                metric_col = col
                break

        if metric_col:
            # Native Python sum
            total_value = sum((row.get(metric_col) or 0) for row in result_data if isinstance(row.get(metric_col), (int, float)))

            if "amount" in metric_col or "revenue" in metric_col:
                explanation = f"Found {row_count} results with a total of ₹{total_value:,.2f}."
            else:
                explanation = f"Found {row_count} results with a total of {total_value:,.0f}."
        else:
            explanation = f"Found {row_count} results."

        # Top result
        if row_count > 0:
            first_row = result_data[0]
            group_col = self._find_group_column(result_data)
            if group_col and group_col in first_row:
                explanation += f" The top result is {first_row[group_col]}."

        return explanation

    def _explain_chart(self, intent: dict[str, Any]) -> str:
        """Explain what the chart shows."""
        chart = intent.get("chart", "bar")
        group_by = intent.get("group_by")

        if chart == "line":
            return "The line chart shows trends over time, making it easy to identify patterns and changes."
        elif chart == "bar":
            if group_by:
                return f"The bar chart compares values across different {group_by}s, making it easy to identify trends."
            return "The bar chart visualizes the results for easy comparison."
        elif chart == "pie":
            return "The pie chart shows the distribution of values as percentages of the whole."
        elif chart == "table":
            return "The table provides a detailed view of all results."

        return ""

    def _find_group_column(self, result_data: list[dict[str, Any]]) -> str | None:
        """Find the grouping column in the records."""
        if not result_data:
            return None
        columns = list(result_data[0].keys())
        candidates = ["name", "category", "city", "month"]
        for col in candidates:
            if col in columns:
                return col
        if columns:
            return columns[0]
        return None
