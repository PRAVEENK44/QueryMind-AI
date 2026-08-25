"""Enhanced Explanation Generator - With LLM insights."""

from typing import Any

from src.llm.client import get_llm_client


class ExplanationGenerator:
    """
    Hybrid explanation generator:
    - Rule-based for simple explanations
    - LLM-powered for human-like insights
    """

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self._fallback = _RuleBasedExplainer()

    def generate(
        self, intent: dict[str, Any], sql_query: str, result: Any, is_refinement: bool = False
    ) -> str:
        """Generate explanation for query and results."""
        # Always get rule-based explanation first
        rule_explanation = self._fallback.explain(intent, sql_query, result, is_refinement)

        # Try to enhance with LLM if available
        if self.use_llm:
            llm = get_llm_client()
            if llm and llm.api_key:
                llm_insights = self._generate_llm_insights(intent, sql_query, result)
                if llm_insights:
                    return f"{rule_explanation}\n\n💡 **Insights:** {llm_insights}"

        return rule_explanation

    def _generate_llm_insights(
        self, intent: dict[str, Any], sql_query: str, result: Any
    ) -> str | None:
        """Generate LLM-powered insights."""
        try:
            llm = get_llm_client()
            if not llm or not llm.api_key:
                return None

            # Prepare data summary
            if result.empty:
                return None

            data_dict = {"data": result.head(10).to_dict("records"), "row_count": len(result)}

            context = f"Query type: {intent.get('aggregation', 'sum')} of {intent.get('metric', 'amount')} grouped by {intent.get('group_by', 'none')}"

            return llm.generate_insights(query="", sql=sql_query, data=data_dict, context=context)
        except Exception as e:
            print(f"LLM insight generation failed: {e}")
            return None

    def generate_simple(self, intent: dict[str, Any]) -> str:
        """Generate simple explanation without data."""
        return self._fallback.explain_simple(intent)


class _RuleBasedExplainer:
    """Rule-based explanation fallback."""

    def explain(
        self, intent: dict[str, Any], sql_query: str, result: Any, is_refinement: bool = False
    ) -> str:
        """Generate rule-based explanation."""
        parts = []

        # Query explanation
        query_exp = self._explain_query(intent, is_refinement)
        parts.append(query_exp)

        # Results explanation
        if result is not None and not result.empty:
            results_exp = self._explain_results(intent, result)
            parts.append(results_exp)

        # Chart explanation
        chart_exp = self._explain_chart(intent)
        parts.append(chart_exp)

        return "\n\n".join(parts)

    def _explain_query(self, intent: dict[str, Any], is_refinement: bool) -> str:
        """Explain what the query does."""
        metric = intent.get("metric", "data")
        agg = intent.get("aggregation", "count")
        group_by = intent.get("group_by")

        explanation = "This query shows "

        if is_refinement:
            explanation = "This refined query shows "

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

        if metric == "amount":
            explanation += "revenue"
        else:
            explanation += metric

        if group_by:
            if group_by == "date":
                explanation += " over time (monthly)"
            elif group_by == "name":
                explanation += " by product"
            elif group_by == "category":
                explanation += " by category"
            elif group_by == "city":
                explanation += " by city"

        filters = intent.get("filters", {})
        filter_parts = []

        if filters.get("city"):
            filter_parts.append(f"orders from {filters['city']}")
        if filters.get("category"):
            filter_parts.append(f"products in {filters['category']}")
        if filters.get("time_range"):
            filter_parts.append(f"in the {filters['time_range'].replace('_', ' ')}")

        if filter_parts:
            explanation += ", filtered by " + ", ".join(filter_parts)

        explanation += "."

        return explanation

    def _explain_results(self, intent: dict[str, Any], result: Any) -> str:
        """Explain what the results show."""
        if result.empty:
            return "No results match your criteria. Try adjusting your filters."

        row_count = len(result)

        metric_col = None
        for col in ["amount", "revenue", "total", "count", "order_count"]:
            if col in result.columns:
                metric_col = col
                break

        if metric_col:
            total_value = result[metric_col].sum()
            if "amount" in metric_col or "revenue" in metric_col:
                explanation = f"Found {row_count} results with a total of ₹{total_value:,.2f} in the selected period."
            else:
                explanation = f"Found {row_count} results with a total of {total_value:,.0f}."
        else:
            explanation = f"Found {row_count} results."

        if row_count > 0:
            first_row = result.iloc[0]
            group_col = self._find_group_column(result)
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
                return f"The bar chart compares values across different {group_by}s, making it easy to identify the highest and lowest values."
            return "The bar chart visualizes the results for easy comparison."
        elif chart == "pie":
            return "The pie chart shows the distribution of values as percentages of the whole."
        elif chart == "table":
            return "The table provides a detailed view of all results."

        return ""

    def _find_group_column(self, df: Any) -> str | None:
        """Find the grouping column."""
        candidates = ["name", "category", "city", "month"]
        for col in candidates:
            if col in df.columns:
                return col
        if len(df.columns) > 0:
            return str(df.columns[0])
        return None

    def explain_simple(self, intent: dict[str, Any]) -> str:
        """Generate simple explanation."""
        metric = intent.get("metric", "data")
        agg = intent.get("aggregation", "sum")
        group_by = intent.get("group_by")

        parts = []
        if agg == "sum":
            parts.append("total")
        elif agg == "avg":
            parts.append("average")
        elif agg == "count":
            parts.append("count of")

        parts.append(metric)

        if group_by:
            parts.append(f"by {group_by}")

        return " ".join(parts)
