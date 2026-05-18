"""Schema Grounding - Ensures LLM uses only valid schema columns."""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class SchemaColumn:
    """Represents a database column."""
    name: str
    type: str
    table: str
    description: Optional[str] = None


class SchemaGrounder:
    """
    Provides schema-grounded context to prevent LLM hallucinations.
    
    Ensures all LLM prompts include explicit schema information.
    """
    
    def __init__(self, schema_info: Dict[str, Any]):
        self.schema_info = schema_info
        self._build_column_map()
    
    def _build_column_map(self):
        """Build map of all valid columns."""
        self.columns: Dict[str, SchemaColumn] = {}
        
        tables = self.schema_info.get("tables", {})
        for table_name, table_data in tables.items():
            for col_name, col_type in table_data.get("columns", {}).items():
                key = f"{table_name}.{col_name}"
                self.columns[key] = SchemaColumn(
                    name=col_name,
                    type=col_type,
                    table=table_name,
                )
                # Also add without table prefix
                self.columns[col_name] = SchemaColumn(
                    name=col_name,
                    type=col_type,
                    table=table_name,
                )
    
    def get_valid_columns(self, table: Optional[str] = None) -> List[str]:
        """Get list of valid columns, optionally filtered by table."""
        if table:
            return [c.name for c in self.columns.values() if c.table == table]
        return list(self.columns.keys())
    
    def build_prompt_context(self) -> str:
        """Build complete schema context for LLM prompts."""
        context = "You must ONLY use these columns in your SQL query:\n\n"
        
        # Tables
        tables = self.schema_info.get("tables", {})
        for table_name, table_data in tables.items():
            context += f"TABLE: {table_name}\n"
            for col_name, col_type in table_data.get("columns", {}).items():
                context += f"  - {col_name} ({col_type})\n"
            context += "\n"
        
        # Term mappings
        mappings = self.schema_info.get("term_mappings", {})
        context += "TERM MAPPINGS (user terms → database columns):\n"
        for term, col in mappings.items():
            context += f"  - {term} → {col}\n"
        
        # Example queries
        context += "\nVALID SQL EXAMPLES:\n"
        context += "  SELECT city, SUM(amount) FROM orders GROUP BY city\n"
        context += "  SELECT category, COUNT(*) FROM orders o JOIN products p ON o.product_id = p.product_id GROUP BY category\n"
        
        return context
    
    def validate_query(self, query: str) -> tuple[bool, Optional[str]]:
        """Validate that query only uses valid columns."""
        import re
        
        # Extract column references from query
        col_pattern = r'\b(\w+)\b'
        used_cols = re.findall(col_pattern, query.upper())
        
        # SQL keywords that aren't columns
        sql_keywords = {
            "SELECT", "FROM", "WHERE", "GROUP", "ORDER", "BY", "HAVING",
            "LIMIT", "JOIN", "LEFT", "RIGHT", "INNER", "ON", "AND", "OR",
            "NOT", "IN", "BETWEEN", "LIKE", "IS", "NULL", "AS", "DISTINCT",
            "SUM", "COUNT", "AVG", "MIN", "MAX", "COALESCE", "CASE", "WHEN",
            "THEN", "ELSE", "END", "ASC", "DESC", "STRFTIME", "INTEGER",
            "TEXT", "REAL", "PRIMARY", "KEY", "FOREIGN", "REFERENCES",
        }
        
        valid_cols = set(self.get_valid_columns())
        valid_cols_upper = {c.upper() for c in valid_cols}
        
        invalid = []
        for col in used_cols:
            if col not in sql_keywords and col not in valid_cols_upper:
                # Check if it's a valid table reference
                if "." in col:
                    table, column = col.split(".", 1)
                    if table.upper() in ["ORDERS", "USERS", "PRODUCTS"]:
                        if column.upper() not in valid_cols_upper:
                            invalid.append(col)
                else:
                    invalid.append(col)
        
        if invalid:
            return False, f"Invalid columns: {', '.join(invalid)}. Use only: {', '.join(sorted(valid_cols)[:10])}..."
        
        return True, None
    
    def build_intent_parser_prompt(self) -> str:
        """Build prompt for intent parser with full schema context."""
        return self.build_prompt_context()
    
    def build_explanation_prompt(self, query: str, sql: str, data_summary: str) -> str:
        """Build prompt for explanation generator."""
        return f"""You are a data analyst. Generate insights from query results.

Query: {query}
SQL: {sql}
Results: {data_summary}

Schema context:
{self.build_prompt_context()}

Provide:
1. What the data shows
2. Key patterns or trends
3. Notable findings
4. Business implications

Be concise and actionable."""


class PromptBuilder:
    """
    Build properly grounded prompts for LLM calls.
    """
    
    def __init__(self, schema_info: Dict[str, Any]):
        self.grounder = SchemaGrounder(schema_info)
    
    def build_intent_prompt(
        self,
        query: str,
        previous_intent: Optional[Dict] = None,
    ) -> tuple[str, str]:
        """Build system and user prompts for intent parsing."""
        system_prompt = f"""You are a query intent parser. Convert natural language to structured JSON.

IMPORTANT: You must ONLY use columns that exist in the database schema below.

{self.grounder.build_prompt_context()}

Output JSON with these fields:
- metric: The metric to query
- aggregation: sum, count, avg, min, or max  
- group_by: Field to group by (optional)
- filters: Dictionary with time_range, city, category
- limit: Number of results
- chart: auto, line, bar, pie, or table

If query is a refinement (words like "only", "just", "now"), merge with previous intent."""
        
        user_prompt = query
        
        if previous_intent:
            user_prompt = f"{query}\n\nPrevious intent: {previous_intent}"
        
        return system_prompt, user_prompt
    
    def build_insight_prompt(
        self,
        query: str,
        sql: str,
        data: Dict,
    ) -> tuple[str, str]:
        """Build prompts for insight generation."""
        system_prompt = self.grounder.build_explanation_prompt(
            query, sql, str(data)[:500]
        )
        
        return system_prompt, "Generate insights from this data"
    
    def validate_and_fix(self, query: str) -> tuple[str, bool]:
        """
        Validate and attempt to fix invalid column references.
        
        Returns:
            Tuple of (fixed_query, was_modified)
        """
        import re
        
        is_valid, error = self.grounder.validate_query(query)
        if is_valid:
            return query, False
        
        # Try to fix common issues
        fixed = query
        
        # Replace common hallucinated terms
        replacements = {
            "sales": "amount",
            "revenue": "amount", 
            "customer": "user_id",
            "buyer": "user_id",
            "product_name": "name",
            "order_date": "date",
            "location": "city",
        }
        
        for wrong, correct in replacements.items():
            fixed = re.sub(rf'\b{wrong}\b', correct, fixed, flags=re.IGNORECASE)
        
        # Validate again
        is_valid, _ = self.grounder.validate_query(fixed)
        
        return fixed, not is_valid


def create_schema_grounder(schema_info: Dict) -> SchemaGrounder:
    """Factory to create schema grounder."""
    return SchemaGrounder(schema_info)


def create_prompt_builder(schema_info: Dict) -> PromptBuilder:
    """Factory to create prompt builder."""
    return PromptBuilder(schema_info)