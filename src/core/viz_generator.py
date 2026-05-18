"""Visualization Generator - Auto-generates charts from query results (Lite Edition)."""
from typing import Optional, Dict, Any, List

class VizGenerator:
    """Generates visualizations from query results using native Python structures."""
    
    def generate_chart(self, result_data: List[Dict[str, Any]], intent: Dict[str, Any], 
                    chart_type: str = "auto") -> Any:
        """
        Generate a chart based on query result records.
        """
        if not result_data:
            return None
            
        columns = list(result_data[0].keys())
        
        # Do not generate a chart for a single scalar value
        if len(result_data) == 1 and len(columns) == 1:
            return None
        
        # Auto-detect chart type if needed
        if chart_type == "auto":
            chart_type = self._detect_chart_type(result_data, columns, intent)
        
        # Generate appropriate chart
        import plotly.express as px
        import plotly.graph_objects as go
        
        if chart_type == "line":
            return self._line_chart(result_data, columns, intent)
        elif chart_type == "bar":
            return self._bar_chart(result_data, columns, intent)
        elif chart_type == "pie":
            return self._pie_chart(result_data, columns, intent)
        elif chart_type == "table":
            return self._table_chart(result_data, columns)
        else:
            return self._bar_chart(result_data, columns, intent)
    
    def _detect_chart_type(self, data: List[Dict], columns: List[str], intent: Dict[str, Any]) -> str:
        """Auto-detect best chart type using native logic."""
        group_by = intent.get("group_by")
        
        # If time-based grouping, use line chart
        column_str = " ".join(columns).lower()
        if group_by == "date" or "month" in column_str or "year" in column_str:
            return "line"
        
        return "bar"
    
    def _line_chart(self, data: List[Dict], columns: List[str], intent: Dict[str, Any]) -> Any:
        """Generate a line chart."""
        import plotly.express as px
        x_col = self._find_column(columns, ["month", "date", "time", "year"])
        y_col = self._find_column(columns, ["amount", "revenue", "sales", "total", "count", "order_count"])
        
        if x_col is None: x_col = columns[0]
        if y_col is None: y_col = columns[-1]
        
        # px supports list of dicts directly
        fig = px.line(data, x=x_col, y=y_col, markers=True)
        
        fig.update_layout(
            title=self._get_chart_title(intent),
            xaxis_title=str(x_col).title(),
            yaxis_title=str(y_col).title(),
            template="plotly_white",
        )
        return fig
    
    def _bar_chart(self, data: List[Dict], columns: List[str], intent: Dict[str, Any]) -> Any:
        """Generate a bar chart."""
        import plotly.express as px
        x_col = self._find_column(columns, ["name", "category", "city", "product"])
        if x_col is None: x_col = columns[0]
        
        y_col = self._find_column(columns, ["amount", "revenue", "sales", "total", "count", "order_count"])
        if y_col is None: y_col = columns[-1]
        
        # Handle coloring categories separately
        has_many = len(data) > 15
        color_val = None if has_many else x_col
        
        fig = px.bar(data, x=x_col, y=y_col, color=color_val, color_discrete_sequence=px.colors.qualitative.Pastel)
        
        fig.update_layout(
            title=self._get_chart_title(intent),
            xaxis_title=str(x_col).title(),
            yaxis_title=str(y_col).title(),
            template="plotly_white",
            showlegend=False if not color_val else True
        )
        
        if len(data) > 5:
            fig.update_xaxes(tickangle=-45)
        
        return fig
    
    def _pie_chart(self, data: List[Dict], columns: List[str], intent: Dict[str, Any]) -> Any:
        """Generate a pie chart."""
        import plotly.express as px
        label_col = self._find_column(columns, ["name", "category", "city"])
        if label_col is None: label_col = columns[0]
        
        value_col = self._find_column(columns, ["amount", "revenue", "sales", "total", "count"])
        if value_col is None: value_col = columns[-1]
        
        fig = px.pie(data, values=value_col, names=label_col, title=self._get_chart_title(intent))
        fig.update_traces(textposition="inside", textinfo="percent+label")
        return fig
    
    def _table_chart(self, data: List[Dict], columns: List[str]) -> Any:
        """Generate a table view."""
        import plotly.graph_objects as go
        fig = go.Figure(data=[go.Table(
            header=dict(
                values=columns,
                fill_color="lightblue",
                align="left"
            ),
            cells=dict(
                values=[[row.get(col) for row in data] for col in columns],
                fill_color="white",
                align="left"
            )
        )])
        return fig
    
    def _find_column(self, columns: List[str], candidates: List[str]) -> Optional[str]:
        """Find a column from candidates."""
        for col in candidates:
            if col in columns:
                return col
        return None
    
    def _get_chart_title(self, intent: Dict[str, Any]) -> str:
        """Generate chart title."""
        metric = intent.get("metric", "Value")
        agg = intent.get("aggregation", "").upper()
        group_by = intent.get("group_by")
        
        title = f"{agg} of {metric.title()}" if agg else metric.title()
        if group_by:
            title += f" by {group_by.title()}"
        return title or "Query Results"