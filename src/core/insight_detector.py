"""Insight Detection Engine - Automatically detect trends, anomalies, top performers (Lite Edition)."""
import math
from dataclasses import dataclass
from typing import Any


@dataclass
class Insight:
    """Represents a detected insight."""
    type: str  # trend, anomaly, top_performer, comparison
    title: str
    description: str
    confidence: float  # 0-1
    data: dict | None = None

class InsightDetector:
    """
    Automatically detect insights from query results using native Python.
    
    Detects:
    - Trends (increasing/decreasing)
    - Anomalies (outliers)
    - Top performers
    - Comparisons
    """

    def detect(self, result_data: list[dict[str, Any]], intent: dict[str, Any]) -> list[Insight]:
        """
        Detect insights from data records.
        """
        if not result_data or len(result_data) < 2:
            return []

        insights = []

        # Detect trends
        trend_insights = self._detect_trends(result_data, intent)
        insights.extend(trend_insights)

        # Detect top performers
        top_insights = self._detect_top_performers(result_data, intent)
        insights.extend(top_insights)

        # Detect anomalies
        anomaly_insights = self._detect_anomalies(result_data, intent)
        insights.extend(anomaly_insights)

        # Detect comparisons
        comp_insights = self._detect_comparisons(result_data, intent)
        insights.extend(comp_insights)

        return insights

    def _detect_trends(self, result_data: list[dict[str, Any]], intent: dict[str, Any]) -> list[Insight]:
        """Detect trends in time-series data using simple slopes."""
        insights = []

        # Check if we have time-series data
        date_col = self._find_column(result_data, ["month", "date", "year"])
        value_col = self._find_column(result_data, ["amount", "revenue", "value", "total"])

        if not date_col or not value_col:
            return insights

        try:
            # Sort by date naturally
            sorted_data = sorted(result_data, key=lambda x: str(x.get(date_col, "")))
            values = [row.get(value_col, 0) for row in sorted_data if isinstance(row.get(value_col), (int, float))]

            if len(values) < 3:
                return insights

            # Simple trend: compare first half vs second half or start vs end
            start_val = values[0]
            end_val = values[-1]

            if start_val == 0 and end_val == 0:
                return insights

            pct_change = ((end_val - start_val) / start_val * 100) if start_val != 0 else 100

            if pct_change > 5:
                insights.append(Insight(
                    type="trend",
                    title="Upward Trend",
                    description=f"Values increased by {pct_change:.1f}% over the period",
                    confidence=0.8 if abs(pct_change) > 10 else 0.5,
                    data={"direction": "up", "pct_change": pct_change},
                ))
            elif pct_change < -5:
                insights.append(Insight(
                    type="trend",
                    title="Downward Trend",
                    description=f"Values decreased by {abs(pct_change):.1f}% over the period",
                    confidence=0.8 if abs(pct_change) > 10 else 0.5,
                    data={"direction": "down", "pct_change": pct_change},
                ))
        except Exception:
            pass

        return insights

    def _detect_top_performers(self, result_data: list[dict[str, Any]], intent: dict[str, Any]) -> list[Insight]:
        """Detect top performing items."""
        insights = []

        group_col = self._find_column(result_data, ["name", "category", "city", "product"])
        value_col = self._find_column(result_data, ["amount", "revenue", "value", "total"])

        if not group_col or not value_col:
            return insights

        try:
            # Sort by value
            sorted_data = sorted(result_data, key=lambda x: x.get(value_col, 0), reverse=True)

            total = sum(row.get(value_col, 0) for row in result_data if isinstance(row.get(value_col), (int, float)))
            if total > 0:
                top_row = sorted_data[0]
                top_value = top_row.get(value_col, 0)
                top_name = top_row.get(group_col, "Unknown")
                concentration = (top_value / total) * 100

                if concentration > 30:
                    insights.append(Insight(
                        type="top_performer",
                        title=f"Leading {group_col.title()}",
                        description=f"{top_name} accounts for {concentration:.1f}% of total",
                        confidence=0.9,
                        data={"name": top_name, "concentration": concentration},
                    ))
        except Exception:
            pass

        return insights

    def _detect_anomalies(self, result_data: list[dict[str, Any]], intent: dict[str, Any]) -> list[Insight]:
        """Detect anomalies/outliers using native math."""
        insights = []

        value_col = self._find_column(result_data, ["amount", "revenue", "value", "total"])
        if not value_col:
            return insights

        try:
            values = [row.get(value_col, 0) for row in result_data if isinstance(row.get(value_col), (int, float))]
            if not values: return []

            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            std = math.sqrt(variance)

            if std == 0: return []

            # Find values more than 2 standard deviations from mean
            threshold = 2
            anomalies = [row for row in result_data if abs((row.get(value_col, 0) or 0) - mean) > threshold * std]

            if 0 < len(anomalies) < len(result_data) * 0.2:
                insights.append(Insight(
                    type="anomaly",
                    title="Notable Outliers Detected",
                    description=f"Found {len(anomalies)} unusual values that deviate significantly from the norm",
                    confidence=0.7,
                    data={"count": len(anomalies)},
                ))
        except Exception:
            pass

        return insights

    def _detect_comparisons(self, result_data: list[dict[str, Any]], intent: dict[str, Any]) -> list[Insight]:
        """Detect interesting comparisons."""
        insights = []

        value_col = self._find_column(result_data, ["amount", "revenue", "value", "total"])
        if not value_col or len(result_data) < 2:
            return insights

        try:
            values = [row.get(value_col, 0) for row in result_data if isinstance(row.get(value_col), (int, float))]
            if not values: return []

            max_val = max(values)
            min_val = min(values)

            if min_val > 0:
                ratio = max_val / min_val
                if ratio > 5:
                    insights.append(Insight(
                        type="comparison",
                        title="High Variation",
                        description=f"Top performer has {ratio:.1f}x more than the lowest",
                        confidence=0.8,
                        data={"ratio": ratio},
                    ))
        except Exception:
            pass

        return insights

    def _find_column(self, result_data: list[dict[str, Any]], candidates: list[str]) -> str | None:
        """Find a column from candidates in memory."""
        if not result_data: return None
        columns = result_data[0].keys()
        for col in candidates:
            if col in columns:
                return col
        return None

def create_insight_detector() -> InsightDetector:
    """Factory to create insight detector."""
    return InsightDetector()
