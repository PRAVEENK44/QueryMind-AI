"""Schema Analyzer - Loads and provides database schema information."""
from typing import Dict, List, Any, Optional
from src.database import get_schema


class SchemaAnalyzer:
    """Analyzes and provides database schema information."""
    
    def __init__(self):
        self._schema = get_schema()
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get full schema information."""
        return self._schema
    
    def get_term_mappings(self) -> Dict[str, str]:
        """Get term to column mappings."""
        return self._schema.get("term_mappings", {})
    
    def get_valid_columns(self, table: str) -> List[str]:
        """Get valid columns for a table."""
        table_schema = self._schema.get("tables", {}).get(table, {})
        return list(table_schema.get("columns", {}).keys())
    
    def get_column_type(self, table: str, column: str) -> Optional[str]:
        """Get column type."""
        table_schema = self._schema.get("tables", {}).get(table, {})
        return table_schema.get("columns", {}).get(column)
    
    def get_valid_values(self, table: str, column: str) -> List[str]:
        """Get sample valid values for a column."""
        table_schema = self._schema.get("tables", {}).get(table, {})
        return table_schema.get("sample_values", {}).get(column, [])
    
    def map_term(self, term: str) -> str:
        """Map a user term to the actual column name."""
        mappings = self.get_term_mappings()
        return mappings.get(term.lower(), term)
    
    def validate_column(self, table: str, column: str) -> bool:
        """Check if a column exists in the schema."""
        return column in self.get_valid_columns(table)
    
    def get_relationships(self) -> List[Dict[str, str]]:
        """Get all table relationships."""
        return self._schema.get("relationships", [])
    
    def get_table_description(self, table: str) -> str:
        """Get description for a specific table."""
        return self._schema.get("tables", {}).get(table, {}).get("description", "")
    
    def get_column_table(self, column: str) -> Optional[str]:
        """Find which table a column belongs to."""
        for table_name, table_info in self._schema.get("tables", {}).items():
            if column in table_info.get("columns", {}):
                return table_name
        return None

    def get_schema_summary(self) -> str:
        """Get a human-readable schema summary including relationships."""
        summary = "Database Schema:\n\n"
        
        for table_name, table_info in self._schema.get("tables", {}).items():
            desc = table_info.get("description", "")
            summary += f"Table: {table_name}"
            if desc:
                summary += f" - {desc}"
            summary += "\n"
            
            for col, col_type in table_info.get("columns", {}).items():
                summary += f"  - {col} ({col_type})\n"
            summary += "\n"
        
        relationships = self.get_relationships()
        if relationships:
            summary += "Relationships:\n"
            for rel in relationships:
                summary += f"  - {rel['from_table']}.{rel['from_col']} → {rel['to_table']}.{rel['to_col']}\n"
            summary += "\n"
        
        summary += "Term Mappings (Common synonyms):\n"
        for term, column in self._schema.get("term_mappings", {}).items():
            summary += f"  - {term} → {column}\n"
        
        return summary
    
    def get_prompt_context(self) -> str:
        """Get schema information formatted for prompt injection."""
        return self.get_schema_summary()