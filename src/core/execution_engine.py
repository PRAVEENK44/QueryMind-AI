"""Execution Engine - Executes SQL queries and returns results (Lite Edition)."""

import os
import re
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

try:
    import sqlglot
    from sqlglot import exp

    SQLGLOT_AVAILABLE = True
except ImportError:
    sqlglot = None
    exp = None
    SQLGLOT_AVAILABLE = False

# Default maximum rows to return for safety
DEFAULT_ROW_LIMIT = 1000


class ExecutionResult:
    """Result of query execution."""

    def __init__(
        self,
        success: bool,
        data: list[dict[str, Any]] | None = None,
        error: str | None = None,
        row_count: int = 0,
        columns: list[str] | None = None,
    ):
        self.success = success
        self.data = data if data is not None else []
        self.error = error
        self.row_count = row_count
        self.columns = columns if columns is not None else []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "row_count": self.row_count,
            "columns": self.columns,
        }

    @property
    def empty(self) -> bool:
        """Compatibility property mimicking Pandas DataFrame.empty"""
        return not self.data


def _detect_dialect(db_url: str) -> str:
    """Detect SQL dialect from database URL."""
    if db_url.startswith("postgresql") or db_url.startswith("postgres"):
        return "postgres"
    return "sqlite"


class ExecutionEngine:
    """Engine for executing SQL queries against any generic database pool without Pandas overhead."""

    def __init__(self, db_path: str = None, row_limit: int = None):
        # Resolve row limit from env or parameter
        if row_limit is None:
            row_limit = int(os.getenv("ROW_LIMIT", str(DEFAULT_ROW_LIMIT)))

        # Resolve absolute path from the project root (two levels up from this file)
        if db_path is None:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            db_path = os.path.join(project_root, "querymind.db")
            # Only use DATABASE_URL override when no explicit path is given (default DB case)
            db_url = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")
        else:
            # Explicit path always wins — critical for user-uploaded databases
            db_url = f"sqlite:///{db_path}"

        self.db_path = db_path
        self.db_url = db_url
        self.dialect = _detect_dialect(db_url)
        self.row_limit = row_limit

        # Use NullPool for serverless/container environments, regular pool otherwise
        if self.dialect == "postgres":
            self.engine = create_engine(db_url, poolclass=NullPool)
        else:
            self.engine = create_engine(db_url)

    def _enforce_row_limit(self, query: str) -> str:
        """Enforce row limit on SELECT queries by appending LIMIT/FETCH if not present."""
        query_stripped = query.strip()
        query_upper = query_stripped.upper()

        # Only enforce on SELECT statements
        if not query_upper.startswith("SELECT"):
            return query_stripped

        # Check if LIMIT already exists (case-insensitive)
        if re.search(r"\bLIMIT\s+\d+", query_upper):
            return query_stripped

        # Check for FETCH FIRST (PostgreSQL standard)
        if re.search(r"\bFETCH\s+FIRST\s+\d+\s+ROWS?", query_upper):
            return query_stripped

        # Append dialect-appropriate limit clause
        if self.dialect == "postgres":
            return f"{query_stripped} FETCH FIRST {self.row_limit} ROWS ONLY"
        return f"{query_stripped} LIMIT {self.row_limit}"

    def _validate_sql_ast(self, query: str) -> tuple[bool, str | None]:
        """Validate SQL using sqlglot AST parsing as backup to keyword blocking.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not SQLGLOT_AVAILABLE:
            return True, None  # Skip if sqlglot not available

        try:
            # Parse the query with appropriate dialect
            parsed = sqlglot.parse(query, dialect=self.dialect)

            if not parsed or len(parsed) == 0:
                return False, "Failed to parse SQL"

            statement = parsed[0]

            # Must be a SELECT statement (or WITH ... SELECT)
            if not isinstance(statement, (exp.Select, exp.With)):
                return False, f"Only SELECT queries are allowed, got {type(statement).__name__}"

            # For WITH statements, check the final statement is SELECT
            if isinstance(statement, exp.With):
                if not statement.expressions:
                    return False, "WITH clause must have at least one expression"
                # Check the main statement
                if not isinstance(statement.args.get("this"), exp.Select):
                    return False, "WITH clause must end with SELECT"

            # Check for forbidden operations in the AST
            forbidden_types = (
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Drop,
                exp.Create,
                exp.Alter,
                exp.TruncateTable,
                exp.Grant,
                exp.Revoke,
                exp.Command,
                exp.Execute,
            )

            for node in statement.walk():
                if isinstance(node, forbidden_types):
                    return False, f"Forbidden operation detected: {type(node).__name__}"

            return True, None

        except Exception as e:
            # If parsing fails, be conservative and reject
            return False, f"SQL validation error: {str(e)}"

    def validate_query(self, query: str) -> tuple[bool, str | None]:
        """Validate a query before execution.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # First: AST-based validation (backup)
        ast_valid, ast_error = self._validate_sql_ast(query)
        if not ast_valid:
            return False, ast_error

        return True, None

    def execute(self, query: str, params: dict = None) -> ExecutionResult:
        """Execute a SQL query and return results as native Python lists/dicts.

        Args:
            query: SQL query string (can use :param_name for parameters)
            params: Optional dictionary of parameters for the query
        """
        # Validate query before execution
        valid, error = self.validate_query(query)
        if not valid:
            return ExecutionResult(success=False, error=error)

        # Enforce row limit
        safe_query = self._enforce_row_limit(query)

        try:
            with self.engine.connect() as conn:
                # Use parameterized query if params provided
                if params:
                    result = conn.execute(text(safe_query), params)
                else:
                    result = conn.execute(text(safe_query))

                # result.keys() provides the column names in SQLAlchemy
                columns = list(result.keys())

                # Fetch all rows and convert to list of dictionaries
                data = []
                for row in result:
                    data.append(dict(zip(columns, row, strict=False)))

            return ExecutionResult(success=True, data=data, row_count=len(data), columns=columns)
        except Exception as e:
            return ExecutionResult(success=False, error=str(e))

    def get_table_preview(self, table_name: str, limit: int = 5) -> list[dict[str, Any]]:
        """Get a preview of a table dynamically as list of dicts."""
        try:
            # Validate table name against allowed characters
            if not re.match(r"^[\w_]+$", table_name):
                return []
            if not isinstance(limit, int) or limit < 1 or limit > 100:
                limit = 5

            with self.engine.connect() as conn:
                # Use parameterized query for limit, table name validated
                query = text(f'SELECT * FROM "{table_name}" LIMIT :limit')
                result = conn.execute(query, {"limit": limit})
                columns = list(result.keys())
                return [dict(zip(columns, row, strict=False)) for row in result]
        except Exception:
            return []

    def get_column_names(self, table_name: str) -> list[str]:
        """Get column names universally via SQLAlchemy Inspector."""
        try:
            insp = inspect(self.engine)
            columns = insp.get_columns(table_name)
            return [col["name"] for col in columns]
        except Exception:
            return []
