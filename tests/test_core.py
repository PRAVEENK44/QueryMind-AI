"""Unit tests for QueryMind AI core components."""

import pytest

from src.agents.schema_analyzer import SchemaAnalyzer
from src.agents.validator import QueryValidator
from src.core.confidence import ConfidenceScorer
from src.core.execution_engine import ExecutionEngine
from src.core.intent_parser import IntentParser, QueryFilters, QueryIntent
from src.core.query_generator import QueryGenerator
from src.database import get_schema


class TestIntentParser:
    """Tests for the rule-based IntentParser."""

    def setup_method(self):
        self.parser = IntentParser()

    def test_parse_simple_count(self):
        intent = self.parser.parse("count all orders")
        assert intent.aggregation == "count"
        # "orders" maps to "order_id" in METRIC_MAP
        assert intent.metric == "order_id"

    def test_parse_sum_revenue(self):
        intent = self.parser.parse("total revenue")
        assert intent.aggregation == "sum"
        assert intent.metric == "amount"

    def test_parse_group_by_city(self):
        intent = self.parser.parse("revenue by city")
        assert intent.group_by == "city"
        assert intent.aggregation == "sum"

    def test_parse_time_range(self):
        intent = self.parser.parse("revenue last_month")
        # The parser extracts "month" from "last_month"
        assert intent.filters.time_range == "month"

    def test_parse_city_filter(self):
        intent = self.parser.parse("revenue in bangalore")
        assert intent.filters.city == "Bangalore"

    def test_refinement(self):
        base = QueryIntent(metric="amount", aggregation="sum", group_by="city")
        refined = self.parser.parse("only bangalore", base)
        assert refined.filters.city == "Bangalore"
        assert refined.metric == "amount"


class TestQueryGenerator:
    """Tests for QueryGenerator."""

    def setup_method(self):
        self.generator = QueryGenerator()
        self.schema = get_schema()

    def test_generate_simple_select(self):
        intent = QueryIntent(metric="amount", aggregation="sum")
        sql, params = self.generator.generate(intent, self.schema)
        assert "SELECT" in sql
        assert "FROM" in sql
        # The generator uses lowercase "sum" in the SQL
        assert "sum" in sql.lower()

    def test_generate_with_group_by(self):
        intent = QueryIntent(metric="amount", aggregation="sum", group_by="city")
        sql, params = self.generator.generate(intent, self.schema)
        assert "GROUP BY" in sql
        assert "city" in sql.lower()

    def test_generate_with_time_filter(self):
        intent = QueryIntent(
            metric="amount", aggregation="sum", filters=QueryFilters(time_range="last_month")
        )
        sql, params = self.generator.generate(intent, self.schema)
        assert "WHERE" in sql
        assert "time_cutoff" in params


class TestExecutionEngine:
    """Tests for ExecutionEngine."""

    def setup_method(self):
        self.engine = ExecutionEngine()

    def test_execute_simple_query(self):
        result = self.engine.execute("SELECT 1 as test")
        assert result.success
        assert result.row_count == 1
        assert result.columns == ["test"]
        assert result.data == [{"test": 1}]

    def test_execute_invalid_query(self):
        result = self.engine.execute("SELECT * FROM nonexistent_table")
        assert not result.success
        assert result.error is not None

    def test_row_limit_enforcement(self):
        """Test that row limit is enforced on large result sets."""
        result = self.engine.execute("SELECT * FROM order_items")
        assert result.success
        assert result.row_count == 1000  # Default ROW_LIMIT

    def test_custom_row_limit(self):
        """Test that custom ROW_LIMIT is respected."""
        engine = ExecutionEngine(row_limit=50)
        result = engine.execute("SELECT * FROM order_items")
        assert result.success
        assert result.row_count == 50

    def test_existing_limit_preserved(self):
        """Test that existing LIMIT clause is not overridden."""
        result = self.engine.execute("SELECT * FROM employees LIMIT 5")
        assert result.success
        assert result.row_count == 5

    def test_ddl_blocked_by_ast(self):
        """Test that DDL statements are blocked by AST validation."""
        for sql in [
            "DROP TABLE employees",
            "CREATE TABLE test (id INTEGER)",
            "ALTER TABLE employees ADD COLUMN test TEXT",
            "TRUNCATE TABLE employees",
        ]:
            result = self.engine.execute(sql)
            assert not result.success, f"Expected {sql} to be blocked"
            assert (
                "Only SELECT queries are allowed" in result.error
                or "Forbidden operation" in result.error
            )

    def test_dml_blocked_by_ast(self):
        """Test that DML statements are blocked by AST validation."""
        for sql in [
            "INSERT INTO employees (dept_id, first_name, last_name, hire_date, status) VALUES (1, 'Test', 'User', '2024-01-01', 'Active')",
            "UPDATE employees SET first_name = 'Hacked' WHERE emp_id = 1",
            "DELETE FROM employees WHERE emp_id = 1",
        ]:
            result = self.engine.execute(sql)
            assert not result.success, f"Expected {sql} to be blocked"
            assert (
                "Only SELECT queries are allowed" in result.error
                or "Forbidden operation" in result.error
            )

    def test_cte_select_allowed(self):
        """Test that CTE with SELECT is allowed."""
        result = self.engine.execute(
            "WITH dept_count AS (SELECT dept_id, COUNT(*) as cnt FROM employees GROUP BY dept_id) SELECT * FROM dept_count"
        )
        assert result.success

    def test_cte_dml_blocked(self):
        """Test that CTE with DML is blocked."""
        result = self.engine.execute(
            "WITH data AS (SELECT 1 as id) INSERT INTO employees SELECT id, 1, 'Test', 'User', '2024-01-01', 'Active' FROM data"
        )
        assert not result.success
        assert (
            "Only SELECT queries are allowed" in result.error
            or "Forbidden operation" in result.error
        )


class TestQueryValidator:
    """Tests for QueryValidator."""

    def setup_method(self):
        self.validator = QueryValidator()
        self.schema = get_schema()

    def test_validate_select_only(self):
        is_valid, error = self.validator.validate("SELECT * FROM orders", self.schema)
        assert is_valid
        assert error is None

    def test_reject_drop(self):
        is_valid, error = self.validator.validate("DROP TABLE orders", self.schema)
        assert not is_valid
        assert "DROP" in error

    def test_reject_update(self):
        is_valid, error = self.validator.validate("UPDATE orders SET amount=100", self.schema)
        assert not is_valid
        assert "UPDATE" in error

    def test_reject_invalid_table(self):
        is_valid, error = self.validator.validate("SELECT * FROM fake_table", self.schema)
        assert not is_valid
        # Error message uppercases the table name
        assert "FAKE_TABLE" in error


class TestSchemaAnalyzer:
    """Tests for SchemaAnalyzer."""

    def setup_method(self):
        self.analyzer = SchemaAnalyzer()

    def test_get_schema_info(self):
        schema = self.analyzer.get_schema_info()
        assert "tables" in schema
        assert "relationships" in schema
        assert "term_mappings" in schema
        assert len(schema["tables"]) == 14

    def test_get_valid_columns(self):
        cols = self.analyzer.get_valid_columns("orders")
        assert "order_id" in cols
        assert "total_amount" in cols
        assert "status" in cols

    def test_map_term(self):
        assert self.analyzer.map_term("revenue") == "total_amount"
        assert self.analyzer.map_term("sales") == "total_amount"
        assert self.analyzer.map_term("client") == "customer_id"


class TestConfidenceScorer:
    """Tests for ConfidenceScorer."""

    def setup_method(self):
        self.scorer = ConfidenceScorer()
        self.engine = ExecutionEngine()
        self.analyzer = SchemaAnalyzer()
        self.schema_info = self.analyzer.get_schema_info()

        # Build schema context string
        tables = self.schema_info.get("tables", {})
        self.schema_context = "Database Schema:\n"
        for table, info in tables.items():
            self.schema_context += f"\nTable: {table}\n"
            for col, col_type in info.get("columns", {}).items():
                self.schema_context += f"  - {col} ({col_type})\n"

    def test_back_translation_hallucination_detection(self):
        """Test that back-translation detects hallucinated SQL."""
        # SQL that doesn't match the query
        sql = "SELECT * FROM departments LIMIT 10"
        query = "Show average salary by department"

        confidence = self.scorer.score(
            original_query=query,
            sql=sql,
            schema_context=self.schema_context,
            schema_info=self.schema_info,
            execution_engine=self.engine,
        )

        # Should detect hallucination (low similarity)
        assert confidence.hallucination_flag is True
        assert confidence.back_translation_score < 0.7

    def test_multi_query_validation_agreement(self):
        """Test multi-query validation detects agreement."""
        # Use a simple, unambiguous query
        sql = "SELECT SUM(budget) FROM departments"
        query = "Total budget across all departments"

        confidence = self.scorer.score(
            original_query=query,
            sql=sql,
            schema_context=self.schema_context,
            schema_info=self.schema_info,
            execution_engine=self.engine,
            force_multi_query=True,
        )

        # Should have multi-query agreement
        assert confidence.multi_query_agreement is not None
        assert confidence.multi_query_agreement >= 0.0
        assert confidence.variant_results is not None
        assert len(confidence.variant_results) >= 2

    def test_overall_confidence_calculation(self):
        """Test overall confidence is calculated correctly."""
        sql = "SELECT SUM(budget) FROM departments"
        query = "Total budget across all departments"

        confidence = self.scorer.score(
            original_query=query,
            sql=sql,
            schema_context=self.schema_context,
            schema_info=self.schema_info,
            execution_engine=self.engine,
            force_multi_query=True,
        )

        assert 0.0 <= confidence.overall_confidence <= 1.0
        assert confidence.back_translation_score is not None
        assert confidence.hallucination_flag is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
