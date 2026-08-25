"""Advanced Error Handling - Better error messages and recovery."""
import re
from dataclasses import dataclass


@dataclass
class QueryError:
    """Structured query error."""
    error_type: str  # syntax, validation, execution, timeout
    message: str
    sql片段: str | None = None
    suggestion: str | None = None
    severity: str = "error"  # error, warning


class ErrorHandler:
    """
    Advanced error handling with suggestions and recovery.
    
    Handles:
    - SQL syntax errors
    - Validation errors
    - Execution errors
    - Timeout errors
    """

    # Common SQL errors and their fixes
    ERROR_PATTERNS = [
        {
            "pattern": r"no such table: (\w+)",
            "type": "syntax",
            "suggestion": "Table '{table}' does not exist. Use: orders, users, or products.",
        },
        {
            "pattern": r"no such column: (\w+)",
            "type": "syntax",
            "suggestion": "Column '{column}' does not exist. Check the schema.",
        },
        {
            "pattern": r"syntax error.*near '(\w+)'",
            "type": "syntax",
            "suggestion": "Check SQL syntax near '{word}'. Common issues: missing quotes, extra commas.",
        },
        {
            "pattern": r"SELECT.*GROUP BY.*order by.*conflict",
            "type": "syntax",
            "suggestion": "When using GROUP BY, all selected columns must be aggregated or in GROUP BY clause.",
        },
        {
            "pattern": r"ambiguous column",
            "type": "syntax",
            "suggestion": "Column name is ambiguous. Use table prefix (e.g., orders.amount).",
        },
    ]

    def handle_error(
        self,
        error: Exception,
        query: str | None = None,
    ) -> QueryError:
        """
        Handle and categorize an error.
        
        Args:
            error: The exception that occurred
            query: The SQL query that caused the error
            
        Returns:
            Structured QueryError with suggestion
        """
        error_msg = str(error)

        # Try to match known patterns
        for pattern_def in self.ERROR_PATTERNS:
            match = re.search(pattern_def["pattern"], error_msg, re.IGNORECASE)
            if match:
                suggestion = pattern_def["suggestion"]
                # Fill in captured groups
                for i, group in enumerate(match.groups()):
                    suggestion = suggestion.replace(f"{{{i}}}", group)
                    suggestion = suggestion.replace(f"{{{pattern_def['pattern'].split(':')[1].strip()}}}", group)

                return QueryError(
                    error_type=pattern_def["type"],
                    message=error_msg,
                    sql片段=query,
                    suggestion=suggestion,
                )

        # Default error handling
        return self._handle_generic_error(error_msg, query)

    def _handle_generic_error(self, error_msg: str, query: str | None) -> QueryError:
        """Handle generic errors with suggestions."""
        error_lower = error_msg.lower()

        # Determine error type
        if "syntax" in error_lower:
            error_type = "syntax"
        elif "validation" in error_lower:
            error_type = "validation"
        elif "timeout" in error_lower:
            error_type = "timeout"
        elif "permission" in error_lower or "denied" in error_lower:
            error_type = "permission"
        else:
            error_type = "execution"

        # Generate suggestion based on error type
        suggestions = {
            "syntax": "Check SQL syntax. Common issues: missing quotes, invalid column names, or malformed queries.",
            "validation": "The query failed validation. Ensure you're using only valid columns from the schema.",
            "timeout": "Query took too long. Try reducing the result set with LIMIT.",
            "permission": "Permission denied. Only SELECT queries are allowed.",
            "execution": "Query execution failed. Check the query and try again.",
        }

        return QueryError(
            error_type=error_type,
            message=error_msg,
            sql片段=query,
            suggestion=suggestions.get(error_type, "An error occurred. Please check your query."),
        )

    def explain_error(self, error: QueryError) -> str:
        """Generate human-readable error explanation."""
        parts = []

        # Error type header
        if error.error_type == "syntax":
            parts.append("**SQL Syntax Error**")
        elif error.error_type == "validation":
            parts.append("**Validation Error**")
        elif error.error_type == "timeout":
            parts.append("**Timeout Error**")
        elif error.error_type == "permission":
            parts.append("**Permission Error**")
        else:
            parts.append("**Execution Error**")

        # Error message
        parts.append(f"\nError: {error.message}")

        # Suggestion
        if error.suggestion:
            parts.append(f"\n💡 **Suggestion:** {error.suggestion}")

        # If we have the problematic SQL
        if error.sql:
            parts.append(f"\n📝 **Query:** ```{error.sql}```")

        return "\n".join(parts)

    def suggest_fix(self, error: QueryError, intent: dict) -> str | None:
        """Suggest a fix based on error and intent."""
        if error.error_type == "syntax":
            return self._suggest_syntax_fix(error, intent)
        elif error.error_type == "validation":
            return self._suggest_validation_fix(error, intent)

        return None

    def _suggest_syntax_fix(self, error: QueryError, intent: dict) -> str | None:
        """Suggest fix for syntax errors."""
        error_msg = error.message.lower()

        if "no such column" in error_msg:
            # Suggest valid columns
            return "Try using: amount, date, city, user_id, product_id, order_id"

        if "no such table" in error_msg:
            return "Use tables: orders, users, products"

        return None

    def _suggest_validation_fix(self, error: QueryError, intent: dict) -> str | None:
        """Suggest fix for validation errors."""
        return "Try simplifying your query or using fewer filters."


class QueryRecovery:
    """
    Attempt to recover from failed queries.
    """

    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler

    def try_recovery(
        self,
        error: Exception,
        intent: dict,
        original_query: str,
    ) -> tuple[str | None, str | None]:
        """
        Attempt to recover from query failure.
        
        Returns:
            Tuple of (recovery_query, recovery_intent) or (None, None)
        """
        query_error = self.error_handler.handle_error(error, original_query)

        # Try different recovery strategies
        strategy = self._select_strategy(query_error)

        if strategy == "simplify":
            return self._simplify_query(intent)
        elif strategy == "relax_filters":
            return self._relax_filters(intent)
        elif strategy == "reduce_limit":
            return self._reduce_limit(intent)

        return None, None

    def _select_strategy(self, error: QueryError) -> str:
        """Select recovery strategy based on error."""
        if error.error_type == "syntax":
            return "simplify"
        elif error.error_type == "timeout":
            return "reduce_limit"
        elif error.error_type == "execution":
            return "relax_filters"
        return "simplify"

    def _simplify_query(self, intent: dict) -> tuple[str | None, dict | None]:
        """Try to simplify query."""
        simplified = dict(intent)
        simplified["group_by"] = None
        simplified["limit"] = 10
        return None, simplified

    def _relax_filters(self, intent: dict) -> tuple[str | None, dict | None]:
        """Try removing filters."""
        simplified = dict(intent)
        simplified["filters"] = {}
        return None, simplified

    def _reduce_limit(self, intent: dict) -> tuple[str | None, dict | None]:
        """Reduce query limit."""
        simplified = dict(intent)
        simplified["limit"] = min(intent.get("limit", 10), 100)
        return None, simplified


def create_error_handler() -> ErrorHandler:
    """Factory to create error handler."""
    return ErrorHandler()


def create_query_recovery() -> QueryRecovery:
    """Factory to create query recovery."""
    return QueryRecovery(create_error_handler())
