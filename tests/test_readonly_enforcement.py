"""Integration tests for database read-only enforcement."""
import os

import psycopg2
import pytest
from psycopg2.errors import InsufficientPrivilege


def get_ro_connection():
    """Get a connection using read-only credentials."""
    # Use environment variables or defaults matching docker-compose/k8s
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "querymind")
    user = os.environ.get("POSTGRES_USER", "querymind_ro_user")
    password = os.environ.get("POSTGRES_PASSWORD", "readonly_password_change_in_prod")

    return psycopg2.connect(
        host=host, port=port, dbname=db, user=user, password=password
    )


def get_rw_connection():
    """Get a connection using read-write credentials (for setup)."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "querymind")
    user = os.environ.get("POSTGRES_RW_USER", "querymind_rw_user")
    password = os.environ.get("POSTGRES_RW_PASSWORD", "readwrite_password_change_in_prod")

    return psycopg2.connect(
        host=host, port=port, dbname=db, user=user, password=password
    )


class TestReadOnlyEnforcement:
    """Verify that read-only user cannot perform write operations."""

    @pytest.fixture(scope="class")
    def rw_conn(self):
        """Read-write connection for test setup."""
        try:
            conn = get_rw_connection()
            yield conn
            conn.close()
        except psycopg2.OperationalError:
            pytest.skip("PostgreSQL not available")

    @pytest.fixture(scope="class")
    def ro_conn(self):
        """Read-only connection for testing."""
        try:
            conn = get_ro_connection()
            yield conn
            conn.close()
        except psycopg2.OperationalError:
            pytest.skip("PostgreSQL not available")

    @pytest.fixture(scope="class")
    def test_table(self, rw_conn):
        """Create a test table using RW connection."""
        with rw_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS test_ro_enforcement (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    value INTEGER
                )
            """)
            rw_conn.commit()
        yield
        # Cleanup
        with rw_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS test_ro_enforcement")
            rw_conn.commit()

    def test_select_allowed(self, ro_conn, test_table):
        """SELECT should work for read-only user."""
        with ro_conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1

    def test_insert_blocked(self, ro_conn, test_table):
        """INSERT should be blocked for read-only user."""
        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute(
                    "INSERT INTO test_ro_enforcement (name, value) VALUES (%s, %s)",
                    ("test", 42)
                )
            ro_conn.rollback()

    def test_update_blocked(self, ro_conn, test_table):
        """UPDATE should be blocked for read-only user."""
        # First insert a row using RW connection
        rw_conn = get_rw_connection()
        with rw_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO test_ro_enforcement (name, value) VALUES (%s, %s) RETURNING id",
                ("original", 100)
            )
            row_id = cur.fetchone()[0]
            rw_conn.commit()
        rw_conn.close()

        # Now try to update as RO user
        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute(
                    "UPDATE test_ro_enforcement SET value = %s WHERE id = %s",
                    (200, row_id)
                )
            ro_conn.rollback()

    def test_delete_blocked(self, ro_conn, test_table):
        """DELETE should be blocked for read-only user."""
        rw_conn = get_rw_connection()
        with rw_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO test_ro_enforcement (name, value) VALUES (%s, %s) RETURNING id",
                ("to_delete", 300)
            )
            row_id = cur.fetchone()[0]
            rw_conn.commit()
        rw_conn.close()

        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute(
                    "DELETE FROM test_ro_enforcement WHERE id = %s",
                    (row_id,)
                )
            ro_conn.rollback()

    def test_create_table_blocked(self, ro_conn):
        """CREATE TABLE should be blocked for read-only user."""
        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute("CREATE TABLE test_create_blocked (id INTEGER)")
            ro_conn.rollback()

    def test_drop_table_blocked(self, ro_conn, test_table):
        """DROP TABLE should be blocked for read-only user."""
        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute("DROP TABLE test_ro_enforcement")
            ro_conn.rollback()

    def test_alter_table_blocked(self, ro_conn, test_table):
        """ALTER TABLE should be blocked for read-only user."""
        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute("ALTER TABLE test_ro_enforcement ADD COLUMN new_col TEXT")
            ro_conn.rollback()

    def test_truncate_blocked(self, ro_conn, test_table):
        """TRUNCATE should be blocked for read-only user."""
        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute("TRUNCATE TABLE test_ro_enforcement")
            ro_conn.rollback()

    def test_grant_revoke_blocked(self, ro_conn):
        """GRANT/REVOKE should be blocked for read-only user."""
        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute("GRANT SELECT ON test_ro_enforcement TO some_role")
            ro_conn.rollback()

    def test_copy_blocked(self, ro_conn, test_table):
        """COPY should be blocked for read-only user."""
        with ro_conn.cursor() as cur:
            with pytest.raises(InsufficientPrivilege):
                cur.execute("COPY test_ro_enforcement TO STDOUT")
            ro_conn.rollback()


class TestReadOnlyUserCanRead:
    """Verify read-only user can perform read operations."""

    @pytest.fixture(scope="class")
    def ro_conn(self):
        try:
            conn = get_ro_connection()
            yield conn
            conn.close()
        except psycopg2.OperationalError:
            pytest.skip("PostgreSQL not available")

    @pytest.fixture(scope="class")
    def rw_conn(self):
        try:
            conn = get_rw_connection()
            yield conn
            conn.close()
        except psycopg2.OperationalError:
            pytest.skip("PostgreSQL not available")

    def test_select_existing_tables(self, ro_conn, rw_conn):
        """Read-only user can query existing tables."""
        # Insert test data via RW
        with rw_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO departments (name, region, budget)
                VALUES ('Test Dept', 'Test Region', 1000000)
                ON CONFLICT DO NOTHING
                RETURNING dept_id
            """)
            rw_conn.commit()

        # Query as RO
        with ro_conn.cursor() as cur:
            cur.execute("SELECT name FROM departments WHERE name = 'Test Dept'")
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "Test Dept"

    def test_select_with_joins(self, ro_conn):
        """Read-only user can perform JOINs."""
        with ro_conn.cursor() as cur:
            cur.execute("""
                SELECT d.name, COUNT(e.emp_id) as emp_count
                FROM departments d
                LEFT JOIN employees e ON d.dept_id = e.dept_id
                GROUP BY d.name
                ORDER BY emp_count DESC
                LIMIT 5
            """)
            rows = cur.fetchall()
            assert len(rows) > 0

    def test_select_with_aggregations(self, ro_conn):
        """Read-only user can use aggregations."""
        with ro_conn.cursor() as cur:
            cur.execute("SELECT SUM(budget) FROM departments")
            row = cur.fetchone()
            assert row[0] is not None

    def test_cte_select_allowed(self, ro_conn):
        """WITH ... SELECT should work for read-only user."""
        with ro_conn.cursor() as cur:
            cur.execute("""
                WITH dept_budget AS (
                    SELECT name, budget FROM departments WHERE budget > 0
                )
                SELECT name FROM dept_budget ORDER BY budget DESC LIMIT 3
            """)
            rows = cur.fetchall()
            assert len(rows) <= 3


# Run with: pytest tests/test_readonly_enforcement.py -v
# Requires PostgreSQL running with the init script applied
# docker-compose -f docker-compose.postgres.yml up -d
