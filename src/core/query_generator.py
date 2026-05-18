"""Query Generator - Converts structured intent into SQL query."""
from datetime import datetime, timedelta
from typing import Optional
import os
from src.core.intent_parser import QueryIntent


class QueryGenerator:
    """Generates SQL queries from structured intent with dynamic join discovery."""
    
    def __init__(self):
        self.aliases = {"orders": "o", "products": "p", "users": "u"}
        
        # Dialect Detection for query adjustments
        db_url = os.getenv("DATABASE_URL", "sqlite")
        self.dialect = "postgresql" if "postgres" in db_url.lower() else "sqlite"
        
    def _format_date(self, column_ref: str) -> str:
        """Dialect-agnostic month extraction"""
        if self.dialect == "postgresql":
            return f"TO_CHAR({column_ref}, 'YYYY-MM')"
        else:
            return f"strftime('%Y-%m', {column_ref})"
    
    def generate(self, intent: QueryIntent, schema_info: dict) -> tuple:
        """Generate SQL query from intent using dynamic schema knowledge.

        Returns:
            Tuple of (sql_query_string, parameters_dict)
        """
        # Pre-process: Identify all required tables
        required_tables = self._get_required_tables(intent, schema_info)

        # Build the query parts
        select_clause = self._build_select(intent, schema_info)
        from_clause = self._build_from()
        join_clause = self._build_join(required_tables, schema_info)
        where_clause, where_params = self._build_where(intent, schema_info)
        group_by_clause = self._build_group_by(intent, schema_info)
        order_by_clause = self._build_order_by(intent)
        limit_clause = self._build_limit(intent)

        # Combine parts
        query_parts = [select_clause, from_clause]

        if join_clause:
            query_parts.append(join_clause)
        if where_clause:
            query_parts.append(where_clause)
        if group_by_clause:
            query_parts.append(group_by_clause)
        if order_by_clause:
            query_parts.append(order_by_clause)
        if limit_clause:
            query_parts.append(limit_clause)

        sql = " ".join(query_parts)
        return sql, where_params

    def _get_required_tables(self, intent: QueryIntent, schema_info: dict) -> set:
        """Identify which tables are needed for the query."""
        tables = {"orders"} # Always start with orders
        
        # Determine priority/preference based on intent
        preference = None
        if "product" in str(intent.metric).lower() or (intent.group_by and "product" in str(intent.group_by).lower()):
            preference = "products"
        elif "user" in str(intent.metric).lower() or (intent.group_by and "user" in str(intent.group_by).lower()):
            preference = "users"

        # Check metric
        metric_col = self._map_term(intent.metric, schema_info)
        m_table = self._find_table(metric_col, schema_info, preference)
        if m_table: tables.add(m_table)
        
        # Check group_by
        if intent.group_by and intent.group_by != "date":
            gb_col = self._map_term(intent.group_by, schema_info)
            gb_table = self._find_table(gb_col, schema_info, preference or m_table)
            if gb_table: tables.add(gb_table)
        
        # Check filters
        if intent.filters.category: tables.add("products")
        if intent.filters.city: tables.add("orders")
        
        return tables

    def _find_table(self, column: str, schema_info: dict, preference: Optional[str] = None) -> Optional[str]:
        """Find which table a column belongs to, prioritizing preference."""
        all_tables = schema_info.get("tables", {})
        
        # Try preference first
        if preference and preference in all_tables:
            if column in all_tables[preference].get("columns", {}):
                return preference
        
        # Heuristic: Default 'name' to 'products' if not specified (common in BI)
        if column == "name" and "products" in all_tables:
            return "products"
        
        # Fallback to searching all tables
        for table_name, table_info in all_tables.items():
            if column in table_info.get("columns", {}):
                return table_name
        return None

    def _build_select(self, intent: QueryIntent, schema_info: dict) -> str:
        """Build SELECT clause with aliases."""
        metric = self._map_term(intent.metric, schema_info)
        agg = intent.aggregation
        m_table = self._find_table(metric, schema_info) or "orders"
        m_alias = self.aliases.get(m_table, "o")
        
        if intent.group_by and intent.group_by != "date":
            gb_col = self._map_term(intent.group_by, schema_info)
            gb_table = self._find_table(gb_col, schema_info) or "orders"
            gb_alias = self.aliases.get(gb_table, "o")
            
            return f"SELECT {gb_alias}.{gb_col} AS {intent.group_by}, {agg}({m_alias}.{metric}) AS {intent.metric}"
        
        elif intent.group_by == "date":
            date_sql = self._format_date("o.date")
            if agg == "count":
                return f"SELECT {date_sql} AS month, COUNT(*) AS order_count"
            return f"SELECT {date_sql} AS month, {agg}({m_alias}.{metric}) AS {intent.metric}"
        
        else:
            if agg == "count":
                return "SELECT COUNT(*) AS total_orders"
            return f"SELECT {agg}({m_alias}.{metric}) AS {intent.metric}"

    def _build_from(self) -> str:
        return "FROM orders o"

    def _build_join(self, required_tables: set, schema_info: dict) -> str:
        """Build JOIN clauses based on relationships."""
        joins = []
        relationships = schema_info.get("relationships", [])
        
        # We start at 'orders'. For any other required table, find relationship
        for table in required_tables:
            if table == "orders": continue
            
            # Find relationship from orders to this table
            for rel in relationships:
                if (rel["from_table"] == "orders" and rel["to_table"] == table):
                    f_alias = self.aliases.get(rel["from_table"])
                    t_alias = self.aliases.get(rel["to_table"])
                    joins.append(f"LEFT JOIN {table} {t_alias} ON {f_alias}.{rel['from_col']} = {t_alias}.{rel['to_col']}")
                    break
        
        return " ".join(joins)

    def _build_where(self, intent: QueryIntent, schema_info: dict) -> tuple:
        """Build WHERE clause with aliases and parameters."""
        conditions = []
        params = {}

        if intent.filters.time_range:
            days = self._get_time_range_days(intent.filters.time_range)
            if days:
                cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                conditions.append("o.date >= :time_cutoff")
                params['time_cutoff'] = cutoff

        if intent.filters.city:
            conditions.append("o.city = :city_filter")
            params['city_filter'] = intent.filters.city.title()

        if intent.filters.category:
            cat = intent.filters.category
            if cat == "Home": cat = "Home & Garden"
            conditions.append("p.category = :category_filter")
            params['category_filter'] = cat

        if intent.filters.start_date:
            conditions.append("o.date >= :start_date")
            params['start_date'] = intent.filters.start_date
        if intent.filters.end_date:
            conditions.append("o.date <= :end_date")
            params['end_date'] = intent.filters.end_date

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        return where_clause, params

    def _build_group_by(self, intent: QueryIntent, schema_info: dict) -> str:
        """Build GROUP BY clause with aliases."""
        if intent.group_by == "date":
            return f"GROUP BY {self._format_date('o.date')}"
        elif intent.group_by:
            gb_col = self._map_term(intent.group_by, schema_info)
            gb_table = self._find_table(gb_col, schema_info) or "orders"
            alias = self.aliases.get(gb_table, "o")
            return f"GROUP BY {alias}.{gb_col}"
        return ""

    def _build_order_by(self, intent: QueryIntent) -> str:
        if intent.group_by:
            order_field = intent.metric if intent.group_by != "date" else ("order_count" if intent.aggregation == "count" else intent.metric)
            return f"ORDER BY {order_field} DESC"
        return ""

    def _build_limit(self, intent: QueryIntent) -> str:
        return f"LIMIT {intent.limit}" if intent.limit > 0 else ""

    def _map_term(self, term: str, schema_info: dict) -> str:
        mappings = schema_info.get("term_mappings", {})
        return mappings.get(term.lower(), term)

    def _get_time_range_days(self, time_range: str) -> Optional[int]:
        mapping = {"last_week": 7, "last_month": 30, "3_months": 90, "6_months": 180, "last_year": 365}
        return mapping.get(time_range.lower(), None)