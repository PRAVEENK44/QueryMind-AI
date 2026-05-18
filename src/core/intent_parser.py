"""Intent Parser - Converts natural language into structured JSON."""
from pydantic import BaseModel, Field
from typing import Optional, Any
import re


class QueryFilters(BaseModel):
    """Filters for the query."""
    time_range: Optional[str] = Field(default=None, description="Time range like 'last_6_months', 'last_year', etc.")
    city: Optional[str] = Field(default=None, description="City filter")
    category: Optional[str] = Field(default=None, description="Category filter")
    start_date: Optional[str] = Field(default=None, description="Start date filter")
    end_date: Optional[str] = Field(default=None, description="End date filter")


class QueryIntent(BaseModel):
    """Structured representation of user query."""
    metric: str = Field(default="", description="The metric to query (e.g., revenue, sales, count)")
    aggregation: str = Field(default="count", description="Aggregation function: sum, count, avg, min, max")
    group_by: Optional[str] = Field(default=None, description="Field to group by")
    filters: QueryFilters = Field(default_factory=QueryFilters, description="Query filters")
    limit: int = Field(default=10, description="Number of results to return")
    chart: str = Field(default="auto", description="Chart type: auto, line, bar, pie, table")
    sql_query: str = Field(default="", description="The explicitly synthesized LLM SQLite executable instruction mapping.")


class IntentParser:
    """Parser that converts natural language to structured query intent."""
    
    # Keyword mappings
    AGGREGATION_MAP = {
        "total": "sum",
        "sum": "sum",
        "average": "avg",
        "avg": "avg",
        "mean": "avg",
        "count": "count",
        "number": "count",
        "max": "max",
        "maximum": "max",
        "min": "min",
        "minimum": "min",
    }
    
    METRIC_MAP = {
        "revenue": "amount",
        "sales": "amount",
        "sales": "amount",
        "amount": "amount",
        "orders": "order_id",
        "transactions": "order_id",
        "customers": "user_id",
        "buyers": "user_id",
        "products": "product_id",
        "items": "product_id",
    }
    
    TIME_RANGES = {
        "last_week": 7,
        "last_month": 30,
        "last_3_months": 90,
        "last_6_months": 180,
        "last_year": 365,
        "this_month": 30,
        "this_year": 365,
    }
    
    CITIES = ["bangalore", "mumbai", "delhi", "chennai", "hyderabad", "kolkata", "pune"]
    
    def parse(self, query: str, previous_intent: Optional[QueryIntent] = None) -> QueryIntent:
        """
        Parse natural language query into structured intent.
        
        If there's a previous intent and query contains refinement keywords,
        update the previous intent instead of starting fresh.
        """
        query_lower = query.lower().strip()
        
        # Check for refinement patterns
        refinement_keywords = ["only", "just", "now", "add", "filtered", "restrict", "with"]
        is_refinement = any(keyword in query_lower for keyword in refinement_keywords)
        
        if is_refinement and previous_intent:
            return self._refine_intent(query, previous_intent)
        
        # Start fresh
        return self._parse_fresh(query_lower)
    
    def _parse_fresh(self, query: str) -> QueryIntent:
        """Parse a fresh query from scratch."""
        # Detect aggregation
        aggregation = self._detect_aggregation(query)
        
        # Detect metric
        metric = self._detect_metric(query)
        
        # Detect group_by
        group_by = self._detect_group_by(query)
        
        # Detect time range
        time_range = self._detect_time_range(query)
        
        # Detect city
        city = self._detect_city(query)
        
        # Detect category
        category = self._detect_category(query)
        
        # Detect limit
        limit = self._detect_limit(query)
        
        # Detect chart type
        chart = self._detect_chart_type(query, group_by, time_range)
        
        filters = QueryFilters(
            time_range=time_range,
            city=city,
            category=category,
        )
        
        return QueryIntent(
            metric=metric,
            aggregation=aggregation,
            group_by=group_by,
            filters=filters,
            limit=limit,
            chart=chart,
        )
    
    def _refine_intent(self, query: str, previous: QueryIntent) -> QueryIntent:
        """
        Refine previous intent based on refinement query.
        """
        # Make a copy of previous intent
        new_intent = QueryIntent(
            metric=previous.metric,
            aggregation=previous.aggregation,
            group_by=previous.group_by,
            filters=QueryFilters(
                time_range=previous.filters.time_range,
                city=previous.filters.city,
                category=previous.filters.category,
                start_date=previous.filters.start_date,
                end_date=previous.filters.end_date,
            ),
            limit=previous.limit,
            chart=previous.chart,
        )
        
        query_lower = query.lower()
        
        # Check for city filter
        city = self._detect_city(query)
        if city:
            new_intent.filters.city = city
        
        # Check for category filter
        category = self._detect_category(query)
        if category:
            new_intent.filters.category = category
        
        # Check for new time range
        time_range = self._detect_time_range(query)
        if time_range:
            new_intent.filters.time_range = time_range
        
        return new_intent
    
    def _detect_aggregation(self, query: str) -> str:
        """Detect aggregation function from query."""
        for keyword, agg in self.AGGREGATION_MAP.items():
            if keyword in query:
                return agg
        # If query contains revenue/sales or "show" with these words, default to sum
        if "revenue" in query or "sales" in query or "spending" in query:
            return "sum"
        return "sum"
    
    def _detect_metric(self, query: str) -> str:
        """Detect the metric being queried."""
        for keyword, metric in self.METRIC_MAP.items():
            if keyword in query:
                return metric
        return "amount"
    
    def _detect_group_by(self, query: str) -> Optional[str]:
        """Detect group by field."""
        query_lower = query.lower()
        
        # Explicit "by X" patterns
        group_patterns = [
            (r"by\s+(product|product\s+name)", "name"),
            (r"by\s+(category|product\s+category)", "category"),
            (r"by\s+(city|location)", "city"),
            (r"by\s+(customer|buyer|user)\s*$", "name"),
            (r"by\s+(customer|buyer|user)\s+by", "name"),
            (r"by\s+(month|year|date|time)", "date"),
        ]
        
        for pattern, field in group_patterns:
            if re.search(pattern, query_lower):
                return field
        
        # Implicit groupings based on keywords
        if "by city" in query_lower or "revenue" in query_lower and "city" in query_lower:
            return "city"
        if "by category" in query_lower or "distribution" in query_lower and "category" in query_lower:
            return "category"
        if "trend" in query_lower or "monthly" in query_lower:
            return "date"
        
        # Handle "top X items" - need to infer grouping
        top_match = re.search(r"(top|first|last)\s+(\d+)", query_lower)
        if top_match:
            if "product" in query_lower:
                return "name"
            if "category" in query_lower:
                return "category"
            if "city" in query_lower:
                return "city"
            if "customer" in query_lower or "user" in query_lower or "buyer" in query_lower:
                return "name"
            if "month" in query_lower:
                return "date"
            if "order" in query_lower or "transaction" in query_lower:
                return "order_id"
        
        return None
    
    def _detect_time_range(self, query: str) -> Optional[str]:
        """Detect time range from query."""
        for keyword, value in self.TIME_RANGES.items():
            if keyword in query:
                # Convert to rough date string
                if "last" in keyword or "this" in keyword:
                    if "month" in keyword:
                        return keyword.replace("last_", "").replace("this_", "")
                    return keyword.replace("last_", "")
        return None
    
    def _detect_city(self, query: str) -> Optional[str]:
        """Detect city from query."""
        for city in self.CITIES:
            if city in query:
                return city.title()
        return None
    
    def _detect_category(self, query: str) -> Optional[str]:
        """Detect category from query."""
        categories = ["electronics", "clothing", "home", "sports", "books", "toys", "food"]
        for cat in categories:
            if cat in query:
                return cat.title() if cat != "home" else "Home & Garden"
        return None
    
    def _detect_limit(self, query: str) -> int:
        """Detect result limit from query."""
        # Look for patterns like "top 5", "last 10", "show 20"
        match = re.search(r"(top|last|first|show)\s+(\d+)", query)
        if match:
            return int(match.group(2))
        
        # Default limits based on context
        if "top" in query:
            return 5
        if "trend" in query or "monthly" in query:
            return 12
        return 10
    
    def _detect_chart_type(self, query: str, group_by: Optional[str], time_range: Optional[str]) -> str:
        """Auto-detect chart type based on query and grouping."""
        query_lower = query.lower()
        
        # If user explicitly specifies chart
        if "line chart" in query_lower or "trend" in query_lower:
            return "line"
        if "bar chart" in query_lower:
            return "bar"
        if "pie chart" in query_lower or "distribution" in query_lower:
            return "pie"
        if "table" in query_lower:
            return "table"
        
        # Auto-detect based on grouping and time
        if group_by == "date" or time_range:
            return "line"
        if group_by in ["city", "category", "name"]:
            return "bar"
        if group_by is None:
            return "bar"
        
        return "auto"