"""Auto Dashboard Generator - Creates complete dashboards from single query."""

from typing import Any


class DashboardGenerator:
    """
    Generates complete dashboards from natural language requests.

    Creates multiple visualizations, KPIs, and insights in one go.
    """

    def __init__(self):
        self.query_definitions = self._build_query_definitions()

    def _build_query_definitions(self) -> dict[str, list[dict]]:
        """Build standard dashboard query definitions."""
        return {
            "sales": [
                {
                    "name": "total_revenue",
                    "sql": "SELECT SUM(amount) as value FROM orders",
                    "metric": "Total Revenue",
                    "format": "currency",
                },
                {
                    "name": "order_count",
                    "sql": "SELECT COUNT(*) as value FROM orders",
                    "metric": "Total Orders",
                    "format": "number",
                },
                {
                    "name": "avg_order_value",
                    "sql": "SELECT AVG(amount) as value FROM orders",
                    "metric": "Avg Order Value",
                    "format": "currency",
                },
                {
                    "name": "revenue_by_month",
                    "sql": "SELECT strftime('%Y-%m', date) as month, SUM(amount) as value FROM orders GROUP BY month ORDER BY month DESC LIMIT 12",
                    "metric": "Monthly Revenue",
                    "chart": "line",
                },
                {
                    "name": "top_products",
                    "sql": "SELECT p.name, SUM(o.amount) as value FROM orders o JOIN products p ON o.product_id = p.product_id GROUP BY p.name ORDER BY value DESC LIMIT 5",
                    "metric": "Top Products",
                    "chart": "bar",
                },
                {
                    "name": "revenue_by_city",
                    "sql": "SELECT city, SUM(amount) as value FROM orders GROUP BY city ORDER BY value DESC",
                    "metric": "Revenue by City",
                    "chart": "bar",
                },
                {
                    "name": "category_distribution",
                    "sql": "SELECT p.category, SUM(o.amount) as value FROM orders o JOIN products p ON o.product_id = p.product_id GROUP BY p.category",
                    "metric": "Category Distribution",
                    "chart": "pie",
                },
            ],
            "products": [
                {
                    "name": "total_products",
                    "sql": "SELECT COUNT(*) as value FROM products",
                    "metric": "Total Products",
                    "format": "number",
                },
                {
                    "name": "products_by_category",
                    "sql": "SELECT category, COUNT(*) as value FROM products GROUP BY category",
                    "metric": "Products by Category",
                    "chart": "bar",
                },
            ],
            "customers": [
                {
                    "name": "total_customers",
                    "sql": "SELECT COUNT(DISTINCT user_id) as value FROM orders",
                    "metric": "Active Customers",
                    "format": "number",
                },
                {
                    "name": "customers_by_city",
                    "sql": "SELECT city, COUNT(DISTINCT user_id) as value FROM orders GROUP BY city",
                    "metric": "Customers by City",
                    "chart": "bar",
                },
            ],
        }

    def generate(self, query: str, execution_engine, schema_info: dict) -> dict[str, Any]:
        """
        Generate complete dashboard.

        Args:
            query: User query (e.g., "show sales dashboard")
            execution_engine: SQL execution engine
            schema_info: Database schema

        Returns:
            Dashboard data with KPIs, charts, insights
        """
        dashboard_type = self._detect_dashboard_type(query)
        queries = self.query_definitions.get(dashboard_type, self.query_definitions["sales"])

        results = {"type": dashboard_type, "kpis": [], "charts": [], "insights": []}

        for q_def in queries:
            result = execution_engine.execute(q_def["sql"])

            if result.success and not result.data.empty:
                if "chart" in q_def:
                    # This is a chart query
                    fig = self._create_chart(result.data, q_def["chart"], q_def["metric"])
                    results["charts"].append(
                        {"title": q_def["metric"], "figure": fig, "type": q_def["chart"]}
                    )
                else:
                    # This is a KPI
                    value = result.data.iloc[0]["value"]
                    results["kpis"].append(
                        {
                            "name": q_def["metric"],
                            "value": value,
                            "format": q_def.get("format", "number"),
                        }
                    )

        # Generate insights
        results["insights"] = self._generate_dashboard_insights(results)

        return results

    def _detect_dashboard_type(self, query: str) -> str:
        """Detect which dashboard to generate."""
        query_lower = query.lower()

        if "product" in query_lower:
            return "products"
        if "customer" in query_lower or "user" in query_lower:
            return "customers"
        return "sales"

    def _create_chart(self, df: Any, chart_type: str, title: str) -> Any:
        """Create a chart from data."""
        import plotly.graph_objects as go

        if chart_type == "line":
            x_col = df.columns[0]
            y_col = df.columns[-1]
            fig = go.Figure(go.Scatter(x=df[x_col], y=df[y_col], mode="lines+markers"))
            fig.update_layout(title=title, template="plotly_white")
            return fig

        elif chart_type == "bar":
            x_col = df.columns[0]
            y_col = df.columns[-1]
            fig = go.Figure(go.Bar(x=df[x_col], y=df[y_col]))
            fig.update_layout(title=title, template="plotly_white")
            if len(df) > 5:
                fig.update_xaxes(tickangle=-45)
            return fig

        elif chart_type == "pie":
            label_col = df.columns[0]
            value_col = df.columns[-1]
            fig = go.Figure(go.Pie(labels=df[label_col], values=df[value_col]))
            fig.update_layout(title=title)
            return fig

        else:
            fig = go.Figure()
            fig.update_layout(title=title)
            return fig

    def _generate_dashboard_insights(self, results: dict) -> list[str]:
        """Generate insights from dashboard data."""
        insights = []

        # Revenue insights
        for kpi in results.get("kpis", []):
            if kpi["name"] == "Total Revenue":
                insights.append(f"Total revenue: ₹{kpi['value']:,.0f}")
            elif kpi["name"] == "Avg Order Value":
                insights.append(f"Average order value: ₹{kpi['value']:,.0f}")

        # Top performer insights
        for chart in results.get("charts", []):
            if chart["type"] == "bar" and "top" in chart["title"].lower():
                df = chart["figure"].data[0]
                if hasattr(df, "y") and len(df.y) > 0:
                    top_item = df.x[0] if hasattr(df, "x") else "item"
                    insights.append(f"Top performer: {top_item}")

        return insights[:3]


class KPICard:
    """Individual KPI card for dashboard."""

    def __init__(self, name: str, value: Any, format_type: str = "number"):
        self.name = name
        self.value = value
        self.format_type = format_type

    def format_value(self) -> str:
        """Format value based on type."""
        if self.format_type == "currency":
            return f"₹{self.value:,.2f}"
        elif self.format_type == "percent":
            return f"{self.value:.1f}%"
        else:
            return f"{self.value:,}"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {"name": self.name, "value": self.format_value(), "raw_value": self.value}


def create_dashboard_generator() -> DashboardGenerator:
    """Factory to create dashboard generator."""
    return DashboardGenerator()
