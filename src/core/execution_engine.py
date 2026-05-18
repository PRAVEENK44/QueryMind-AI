"""Execution Engine - Executes SQL queries and returns results (Lite Edition)."""
import os
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, inspect, text

class ExecutionResult:
    """Result of query execution."""
    def __init__(self, success: bool, data: Optional[List[Dict[str, Any]]] = None, 
                 error: Optional[str] = None, row_count: int = 0, columns: Optional[List[str]] = None):
        self.success = success
        self.data = data if data is not None else []
        self.error = error
        self.row_count = row_count
        self.columns = columns if columns is not None else []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "row_count": self.row_count,
            "columns": self.columns
        }
    
    @property
    def empty(self) -> bool:
        """Compatibility property mimicking Pandas DataFrame.empty"""
        return not self.data

class ExecutionEngine:
    """Engine for executing SQL queries against any generic database pool without Pandas overhead."""
    
    def __init__(self, db_path: str = None):
        # Resolve absolute path from the project root (two levels up from this file)
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(project_root, "querymind.db")
            # Only use DATABASE_URL override when no explicit path is given (default DB case)
            db_url = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")
        else:
            # Explicit path always wins — critical for user-uploaded databases
            db_url = f"sqlite:///{db_path}"
        self.db_path = db_path
        self.engine = create_engine(db_url)
    
    def execute(self, query: str, params: dict = None) -> ExecutionResult:
        """Execute a SQL query and return results as native Python lists/dicts.

        Args:
            query: SQL query string (can use :param_name for parameters)
            params: Optional dictionary of parameters for the query
        """
        try:
            with self.engine.connect() as conn:
                # Use parameterized query if params provided
                if params:
                    result = conn.execute(text(query), params)
                else:
                    result = conn.execute(text(query))

                # result.keys() provides the column names in SQLAlchemy
                columns = list(result.keys())

                # Fetch all rows and convert to list of dictionaries
                data = []
                for row in result:
                    data.append(dict(zip(columns, row)))

            return ExecutionResult(
                success=True,
                data=data,
                row_count=len(data),
                columns=columns
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
            )
    
    def get_table_preview(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get a preview of a table dynamically as list of dicts."""
        try:
            # Validate table name against allowed characters
            import re
            if not re.match(r'^[\w_]+$', table_name):
                return []
            if not isinstance(limit, int) or limit < 1 or limit > 100:
                limit = 5

            with self.engine.connect() as conn:
                # Use parameterized query for limit, table name validated
                query = text(f"SELECT * FROM \"{table_name}\" LIMIT :limit")
                result = conn.execute(query, {"limit": limit})
                columns = list(result.keys())
                return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            return []
    
    def get_column_names(self, table_name: str) -> List[str]:
        """Get column names universally via SQLAlchemy Inspector."""
        try:
            insp = inspect(self.engine)
            columns = insp.get_columns(table_name)
            return [col['name'] for col in columns]
        except Exception as e:
            return []