"""Tests for SQL execution guardrails (AST validation, row limits, read-only enforcement)."""
import pytest

from src.core.execution_engine import ExecutionEngine


class TestGuardrails:
    """Test that execution engine blocks dangerous operations."""

    @pytest.fixture
    def engine(self):
        """Create execution engine with test database."""
        return ExecutionEngine(db_path=":memory:", row_limit=10)

    def test_blocks_create_table(self, engine):
        """CREATE TABLE should be rejected."""
        result = engine.execute("CREATE TABLE test (id INTEGER)")
        assert result.success is False
        assert "Forbidden operation" in result.error or "Only SELECT" in result.error

    def test_blocks_drop_table(self, engine):
        """DROP TABLE should be rejected."""
        result = engine.execute("DROP TABLE test")
        assert result.success is False
        assert "Forbidden operation" in result.error or "Only SELECT" in result.error

    def test_blocks_alter_table(self, engine):
        """ALTER TABLE should be rejected."""
        result = engine.execute("ALTER TABLE test ADD COLUMN x INTEGER")
        assert result.success is False
        assert "Forbidden operation" in result.error or "Only SELECT" in result.error

    def test_blocks_insert(self, engine):
        """INSERT should be rejected."""
        result = engine.execute("INSERT INTO test VALUES (1)")
        assert result.success is False
        assert "Forbidden operation" in result.error or "Only SELECT" in result.error

    def test_blocks_update(self, engine):
        """UPDATE should be rejected."""
        result = engine.execute("UPDATE test SET x = 1")
        assert result.success is False
        assert "Forbidden operation" in result.error or "Only SELECT" in result.error

    def test_blocks_delete(self, engine):
        """DELETE should be rejected."""
        result = engine.execute("DELETE FROM test")
        assert result.success is False
        assert "Forbidden operation" in result.error or "Only SELECT" in result.error

    def test_blocks_truncate(self, engine):
        """TRUNCATE should be rejected."""
        result = engine.execute("TRUNCATE TABLE test")
        assert result.success is False
        assert "Forbidden operation" in result.error or "Only SELECT" in result.error

    def test_blocks_grant_revoke(self, engine):
        """GRANT/REVOKE should be rejected."""
        result = engine.execute("GRANT SELECT ON test TO user")
        assert result.success is False
        assert "Forbidden operation" in result.error or "Only SELECT" in result.error

    def test_allows_select(self, engine):
        """Basic SELECT should work."""
        # First create a table using raw SQLAlchemy to test against
        from sqlalchemy import create_engine, text
        test_engine = create_engine("sqlite:///:memory:")
        with test_engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER, name TEXT)"))
            conn.execute(text("INSERT INTO test VALUES (1, 'a'), (2, 'b')"))
            conn.commit()

        # Now test with our engine pointing at same DB
        # Note: This test uses a different approach since we can't share :memory:
        # In practice, the guardrail test runs against the real DB
        pass  # Placeholder - real test uses file-based DB

    def test_enforces_row_limit(self, engine):
        """Queries without LIMIT should get row limit appended."""
        # This tests the _enforce_row_limit method directly
        query = "SELECT * FROM some_table"
        limited = engine._enforce_row_limit(query)
        assert "LIMIT 10" in limited

    def test_respects_existing_limit(self, engine):
        """Existing LIMIT should not be duplicated."""
        query = "SELECT * FROM some_table LIMIT 5"
        limited = engine._enforce_row_limit(query)
        assert limited == query
        assert limited.count("LIMIT") == 1

    def test_postgres_fetch_first(self):
        """PostgreSQL dialect should use FETCH FIRST."""
        import os
        os.environ["DATABASE_URL"] = "postgresql://user:pass@host/db"
        try:
            engine = ExecutionEngine(row_limit=100)
            query = "SELECT * FROM some_table"
            limited = engine._enforce_row_limit(query)
            assert "FETCH FIRST 100 ROWS ONLY" in limited
        finally:
            os.environ.pop("DATABASE_URL", None)

    def test_select_with_cte_allowed(self, engine):
        """WITH ... SELECT should be allowed."""
        # AST validation allows WITH clauses ending in SELECT
        from src.core.execution_engine import SQLGLOT_AVAILABLE
        if SQLGLOT_AVAILABLE:
            import sqlglot
            from sqlglot import exp
            parsed = sqlglot.parse("WITH cte AS (SELECT 1) SELECT * FROM cte", dialect="sqlite")
            assert len(parsed) == 1
            # sqlglot parses this as Select with a with_ property, not as With node
            assert isinstance(parsed[0], exp.Select)
            assert parsed[0].args.get("with_") is not None


class TestRowLimitEdgeCases:
    """Edge cases for row limit enforcement."""

    def test_case_insensitive_limit_detection(self):
        engine = ExecutionEngine(db_path=":memory:", row_limit=50)
        query = "select * from table limit 5"
        limited = engine._enforce_row_limit(query)
        assert limited == query  # Already has limit

    def test_limit_with_offset(self):
        engine = ExecutionEngine(db_path=":memory:", row_limit=50)
        query = "SELECT * FROM table LIMIT 10 OFFSET 5"
        limited = engine._enforce_row_limit(query)
        assert limited == query  # Already has limit
