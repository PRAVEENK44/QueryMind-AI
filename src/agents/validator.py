"""Validator Agent - Validates SQL queries for safety and validity."""
from typing import Dict, List, Optional, Tuple
import re


class ValidationError(Exception):
    """Raised when a query fails validation."""
    pass


class QueryValidator:
    """Validates SQL queries for safety and schema compliance."""
    
    # Dangerous SQL keywords that should never be allowed
    DANGEROUS_KEYWORDS = [
        "DROP",
        "DELETE",
        "UPDATE",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "INSERT",
        "GRANT",
        "REVOKE",
        "EXEC",
        "EXECUTE",
    ]
    
    # Valid SQL keywords for SELECT queries
    ALLOWED_KEYWORDS = [
        "SELECT",
        "FROM",
        "WHERE",
        "GROUP BY",
        "ORDER BY",
        "HAVING",
        "LIMIT",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "ON",
        "AND",
        "OR",
        "NOT",
        "IN",
        "BETWEEN",
        "LIKE",
        "IS",
        "NULL",
        "AS",
        "DISTINCT",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
    ]
    
    # Valid aggregation functions
    AGGREGATION_FUNCTIONS = [
        "SUM",
        "COUNT",
        "AVG",
        "MIN",
        "MAX",
        "COALESCE",
        "NULLIF",
    ]
    
    # Valid table names - dynamically overridden in validate() from live schema_info
    VALID_TABLES = ["employees", "departments", "salaries", "customers", "campaigns",
                    "interactions", "inventory", "warehouses", "shipments", "suppliers",
                    "invoices", "orders", "order_items", "products"]

    # Valid column names - must match database schema
    VALID_COLUMNS = {
        "orders": ["order_id", "user_id", "total_amount", "status", "shipping_city", "date"],
        "users": ["user_id", "name", "city", "signup_date", "is_premium"],
        "products": ["product_id", "name", "category", "brand", "base_price", "stock_quantity"],
        "order_items": ["item_id", "order_id", "product_id", "quantity", "unit_price", "subtotal"],
        "reviews": ["review_id", "user_id", "product_id", "rating", "review_text", "review_date"],
    }
    
    def validate(self, query: str, schema_info: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate a SQL query.
        
        Args:
            query: SQL query to validate
            schema_info: Schema information for column validation
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        query_upper = query.upper()
        
        # Check for dangerous keywords
        for keyword in self.DANGEROUS_KEYWORDS:
            if re.search(rf"\b{keyword}\b", query_upper):
                return False, f"Query contains forbidden keyword '{keyword}'. Only SELECT queries are allowed."
        
        # Must start with SELECT
        if not query_upper.strip().startswith("SELECT"):
            return False, "Only SELECT queries are allowed."
        
        # Build valid tables dynamically from live schema
        live_tables = set(schema_info.get("tables", {}).keys())
        valid_tables = live_tables if live_tables else {t.lower() for t in self.VALID_TABLES}
        
        # Validate table names (case-insensitive)
        table_pattern = r"FROM\s+(\w+)|JOIN\s+(\w+)"
        table_matches = re.findall(table_pattern, query_upper)
        for match_tuple in table_matches:
            for table in match_tuple:
                if table and table.lower() not in valid_tables:
                    return False, f"Invalid table '{table}'. Valid tables: {', '.join(sorted(valid_tables))}"
        
        return True, None
    
    def validate_intent(self, query_intent, schema_info: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate the structured query intent.
        
        Args:
            query_intent: QueryIntent object
            schema_info: Schema information
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        term_mappings = schema_info.get("term_mappings", {})
        
        # Validate metric
        if query_intent.metric:
            mapped_metric = term_mappings.get(query_intent.metric.lower(), query_intent.metric)
            if not self._validate_column_exists(mapped_metric):
                return False, f"Invalid metric '{query_intent.metric}'. Not found in schema."
        
        # Validate group_by
        if query_intent.group_by:
            # Map the term first
            mapped_group = term_mappings.get(query_intent.group_by.lower(), query_intent.group_by)
            if not self._validate_column_exists(mapped_group):
                # Try direct column name
                if not self._validate_column_exists(query_intent.group_by):
                    pass  # Will handle in SQL generation
        
        return True, None
    
    def _validate_column_exists(self, column: str) -> bool:
        """Check if column exists in any table."""
        for cols in self.VALID_COLUMNS.values():
            if column in cols:
                return True
        return False
    
    def get_allowed_columns(self) -> Dict[str, List[str]]:
        """Get all allowed columns."""
        return self.VALID_COLUMNS.copy()