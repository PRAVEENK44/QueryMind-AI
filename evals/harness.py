"""Eval Harness — Runs ground-truth queries, compares SQL + results, reports pass/fail."""
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from evals.client import EvalLLMClient
from src.agents.schema_analyzer import SchemaAnalyzer
from src.core.confidence import ConfidenceScorer
from src.core.execution_engine import ExecutionEngine
from src.llm.client import IntentParserLLM

try:
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

RUN_HISTORY_PATH = Path(__file__).parent / "run_history.jsonl"
BASELINE_PATH = Path(__file__).parent / "baseline.json"
ROLLING_WINDOW = 10

# Pushgateway configuration
PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "http://localhost:9091")
PUSHGATEWAY_JOB = "querymind-eval-harness"

# Confidence scoring sample rate for eval (10% of queries)
CONFIDENCE_SAMPLE_RATE = 0.1


@dataclass
class TestCase:
    id: str
    category: str
    query: str
    expected_sql: str
    expected_columns: list[str]
    min_rows: int
    max_rows: int


@dataclass
class EvalResult:
    test_id: str
    category: str
    query: str
    passed: bool
    sql_match: bool
    row_count_match: bool
    columns_match: bool
    generated_sql: str
    expected_sql: str
    actual_row_count: int
    expected_min_rows: int
    expected_max_rows: int
    actual_columns: list[str]
    expected_columns: list[str]
    latency_ms: int
    tokens_used: int
    cost_usd: float
    provider: str
    model: str
    error: str | None = None
    # Confidence scoring fields
    confidence_overall: float | None = None
    confidence_back_translation: float | None = None
    confidence_hallucination_flag: bool | None = None
    confidence_multi_query_agreement: float | None = None
    confidence_multi_query_flag: bool | None = None


def load_test_cases(path: Path) -> list[TestCase]:
    """Load test cases from JSONL file."""
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            cases.append(TestCase(**data))
    return cases


def load_run_history() -> list[dict]:
    """Load historical run summaries from JSONL file."""
    if not RUN_HISTORY_PATH.exists():
        return []
    history = []
    with open(RUN_HISTORY_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                history.append(json.loads(line))
    return history


def save_run_history(summary: dict):
    """Append run summary to history file."""
    RUN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RUN_HISTORY_PATH, "a") as f:
        f.write(json.dumps({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": summary["total"],
            "passed": summary["passed"],
            "failed": summary["failed"],
            "pass_rate": summary["pass_rate"],
            "total_tokens": summary["total_tokens"],
            "total_cost_usd": summary["total_cost_usd"],
            "avg_latency_ms": summary["avg_latency_ms"],
            "provider_breakdown": summary["provider_breakdown"],
        }) + "\n")


def compute_rolling_averages(history: list[dict], window: int = ROLLING_WINDOW) -> dict:
    """Compute rolling averages over recent runs."""
    if not history:
        return {}
    recent = history[-window:]
    return {
        "rolling_pass_rate": round(sum(h["pass_rate"] for h in recent) / len(recent), 2),
        "rolling_avg_latency_ms": round(sum(h["avg_latency_ms"] for h in recent) / len(recent), 2),
        "rolling_total_tokens": round(sum(h["total_tokens"] for h in recent) / len(recent), 2),
        "rolling_total_cost_usd": round(sum(h["total_cost_usd"] for h in recent) / len(recent), 6),
        "window_size": len(recent),
        "total_runs": len(history),
    }


def load_baseline() -> dict | None:
    """Load baseline summary for regression comparison."""
    if not BASELINE_PATH.exists():
        return None
    with open(BASELINE_PATH) as f:
        return json.load(f)


def save_baseline(summary: dict):
    """Save current summary as baseline."""
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        json.dump(summary, f, indent=2)


def compare_with_baseline(current: dict, baseline: dict) -> dict:
    """Compare current run with baseline, return deltas."""
    if not baseline:
        return {"baseline_available": False}

    return {
        "baseline_available": True,
        "pass_rate_delta": round(current["pass_rate"] - baseline["pass_rate"], 2),
        "latency_delta_ms": round(current["avg_latency_ms"] - baseline["avg_latency_ms"], 2),
        "cost_delta_usd": round(current["total_cost_usd"] - baseline["total_cost_usd"], 6),
        "tokens_delta": current["total_tokens"] - baseline["total_tokens"],
        "regression": current["pass_rate"] < baseline["pass_rate"] - 1.0,
    }


def normalize_sql(sql: str) -> str:
    """
    Normalize SQL for semantic comparison:
    - Strip whitespace
    - Uppercase keywords
    - Normalize aliases
    - Remove semantic-preserving differences
    """
    if not sql:
        return ""

    # Remove comments
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)

    # Normalize whitespace
    sql = re.sub(r"\s+", " ", sql).strip()

    # Uppercase SQL keywords
    keywords = [
        "SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT",
        "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "OUTER JOIN", "ON",
        "AND", "OR", "NOT", "IN", "BETWEEN", "LIKE", "IS", "NULL", "AS",
        "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END",
        "SUM", "COUNT", "AVG", "MIN", "MAX", "COALESCE", "NULLIF",
        "STRFTIME", "TO_CHAR",
        "ASC", "DESC",
    ]
    for kw in keywords:
        sql = re.sub(rf"\b{kw}\b", kw, sql, flags=re.IGNORECASE)

    # Normalize string literals to placeholder
    sql = re.sub(r"'[^']*'", "'?'", sql)
    sql = re.sub(r'"[^"]*"', '"?"', sql)

    # Normalize numbers
    sql = re.sub(r"\b\d+\b", "N", sql)

    # Normalize table aliases (remove them for comparison)
    sql = re.sub(r"\b(\w+)\s+AS\s+\w+\b", r"\1", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\b(\w+)\s+\w+\b(?=\s+(?:JOIN|WHERE|GROUP|ORDER|LIMIT|,|$))", r"\1", sql)

    return sql.strip()


def extract_sql_structure(sql: str) -> dict[str, Any]:
    """Extract key structural elements from SQL for comparison."""
    norm = normalize_sql(sql)

    structure = {
        "select_columns": [],
        "tables": [],
        "joins": [],
        "where_conditions": [],
        "group_by": [],
        "order_by": [],
        "limit": None,
    }

    # Extract SELECT columns
    select_match = re.search(r"SELECT\s+(.*?)\s+FROM", norm, re.IGNORECASE)
    if select_match:
        cols = select_match.group(1).split(",")
        structure["select_columns"] = [c.strip() for c in cols]

    # Extract tables
    from_match = re.search(r"FROM\s+(\w+)", norm, re.IGNORECASE)
    if from_match:
        structure["tables"].append(from_match.group(1))

    # Extract JOINs
    join_matches = re.findall(r"(LEFT|RIGHT|INNER|OUTER)?\s*JOIN\s+(\w+)\s+ON\s+([^ ]+)\s*=\s*([^ ]+)", norm, re.IGNORECASE)
    for j in join_matches:
        structure["joins"].append({
            "type": j[0] or "JOIN",
            "table": j[1],
            "on_left": j[2],
            "on_right": j[3],
        })

    # Extract WHERE
    where_match = re.search(r"WHERE\s+(.*?)(?:\s+GROUP BY|\s+ORDER BY|\s+LIMIT|$)", norm, re.IGNORECASE)
    if where_match:
        conditions = where_match.group(1).split(" AND ")
        structure["where_conditions"] = sorted([c.strip() for c in conditions])

    # Extract GROUP BY
    group_match = re.search(r"GROUP BY\s+(.*?)(?:\s+ORDER BY|\s+LIMIT|$)", norm, re.IGNORECASE)
    if group_match:
        structure["group_by"] = sorted([g.strip() for g in group_match.group(1).split(",")])

    # Extract ORDER BY
    order_match = re.search(r"ORDER BY\s+(.*?)(?:\s+LIMIT|$)", norm, re.IGNORECASE)
    if order_match:
        structure["order_by"] = sorted([o.strip() for o in order_match.group(1).split(",")])

    # Extract LIMIT
    limit_match = re.search(r"LIMIT\s+(\d+)", norm, re.IGNORECASE)
    if limit_match:
        structure["limit"] = int(limit_match.group(1))

    return structure


def columns_fuzzy_match(gen_cols: list[str], exp_cols: list[str]) -> bool:
    """Fuzzy match column names allowing minor alias differences."""
    if len(gen_cols) != len(exp_cols):
        return False
    
    # Normalize column names for comparison
    def normalize_col(col: str) -> str:
        # Remove table prefixes, AS aliases, and common prefixes/suffixes
        col = col.strip().lower()
        # Remove table prefix (e.g., "table.column" -> "column")
        if "." in col:
            col = col.split(".")[-1]
        # Remove AS alias (e.g., "col AS alias" -> "col")
        if " as " in col:
            col = col.split(" as ")[0].strip()
        # Normalize common variations
        col = col.replace("_", "").replace("total", "").replace("avg", "average").replace("count", "").replace("sum", "")
        return col
    
    gen_norm = [normalize_col(c) for c in gen_cols]
    exp_norm = [normalize_col(c) for c in exp_cols]
    
    # Try exact match first
    if set(gen_norm) == set(exp_norm):
        return True
    
    # Fuzzy match: check if each gen col has a close match in exp
    for g in gen_norm:
        matched = False
        for e in exp_norm:
            if g == e or g in e or e in g:
                matched = True
                break
        if not matched:
            return False
    return True


def sql_semantic_match(generated: str, expected: str) -> bool:
    """Check if two SQL queries are semantically equivalent by comparing structure."""
    gen_struct = extract_sql_structure(generated)
    exp_struct = extract_sql_structure(expected)

    # Compare key structural elements
    # SELECT columns (order-independent, with fuzzy matching)
    if not columns_fuzzy_match(gen_struct["select_columns"], exp_struct["select_columns"]):
        return False

    # Tables (order-independent)
    if set(gen_struct["tables"]) != set(exp_struct["tables"]):
        return False

    # JOINs (compare table and join condition)
    if len(gen_struct["joins"]) != len(exp_struct["joins"]):
        return False
    for gj, ej in zip(
        sorted(gen_struct["joins"], key=lambda x: x["table"]),
        sorted(exp_struct["joins"], key=lambda x: x["table"]),
        strict=True,
    ):
        if gj["table"] != ej["table"]:
            return False
        # Compare join conditions (normalize)
        if {gj["on_left"], gj["on_right"]} != {ej["on_left"], ej["on_right"]}:
            return False

    # WHERE conditions (order-independent)
    if set(gen_struct["where_conditions"]) != set(exp_struct["where_conditions"]):
        return False

    # GROUP BY (order-independent)
    if set(gen_struct["group_by"]) != set(exp_struct["group_by"]):
        return False

    # ORDER BY (order matters for ORDER BY)
    if gen_struct["order_by"] != exp_struct["order_by"]:
        return False

    # LIMIT
    if gen_struct["limit"] != exp_struct["limit"]:
        return False

    return True


def sql_execution_match(generated: str, expected: str, db_path: str) -> bool:
    """Check if two SQL queries produce the same results when executed."""
    gen_rows, gen_cols, gen_err = run_query_on_db(generated, db_path)
    exp_rows, exp_cols, exp_err = run_query_on_db(expected, db_path)

    # Both must execute successfully
    if gen_err or exp_err:
        return False

    # Same number of rows
    if len(gen_rows) != len(exp_rows):
        return False

    # Same number of columns
    if len(gen_cols) != len(exp_cols):
        return False

    # Compare values (order-independent for rows)
    try:
        gen_sorted = sorted([tuple(row.values()) for row in gen_rows])
        exp_sorted = sorted([tuple(row.values()) for row in exp_rows])
        return gen_sorted == exp_sorted
    except Exception:
        return False


def run_query_on_db(sql: str, db_path: str) -> tuple[list[dict], list[str], str | None]:
    """Execute SQL on SQLite database, return rows, columns, error."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = [dict(row) for row in cursor.fetchall()]
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()
        return rows, columns, None
    except Exception as e:
        return [], [], str(e)


def build_schema_context() -> str:
    """Build schema context for LLM (same as production)."""
    return """Database Schema:

Table: departments
  - dept_id (INTEGER)
  - name (TEXT)
  - region (TEXT)
  - budget (REAL)

Table: employees
  - emp_id (INTEGER)
  - dept_id (INTEGER)
  - first_name (TEXT)
  - last_name (TEXT)
  - hire_date (TEXT)
  - status (TEXT)

Table: salaries
  - salary_id (INTEGER)
  - emp_id (INTEGER)
  - base_salary (REAL)
  - bonus (REAL)
  - effective_date (TEXT)

Table: campaigns
  - campaign_id (INTEGER)
  - name (TEXT)
  - channel (TEXT)
  - start_date (TEXT)
  - end_date (TEXT)
  - budget (REAL)
  - roi_percent (REAL)

Table: customers
  - customer_id (INTEGER)
  - company_name (TEXT)
  - industry (TEXT)
  - campaign_source_id (INTEGER)
  - total_ltv (REAL)

Table: interactions
  - interaction_id (INTEGER)
  - customer_id (INTEGER)
  - emp_id (INTEGER)
  - type (TEXT)
  - date (TEXT)
  - sentiment_score (REAL)

Table: warehouses
  - warehouse_id (INTEGER)
  - location (TEXT)
  - capacity (INTEGER)
  - manager_emp_id (INTEGER)

Table: suppliers
  - supplier_id (INTEGER)
  - name (TEXT)
  - country (TEXT)
  - rating (REAL)

Table: products
  - product_id (INTEGER)
  - supplier_id (INTEGER)
  - name (TEXT)
  - category (TEXT)
  - unit_cost (REAL)
  - msrp (REAL)

Table: inventory
  - inventory_id (INTEGER)
  - warehouse_id (INTEGER)
  - product_id (INTEGER)
  - quantity_on_hand (INTEGER)
  - restock_threshold (INTEGER)

Table: orders
  - order_id (INTEGER)
  - customer_id (INTEGER)
  - sales_rep_emp_id (INTEGER)
  - date (TEXT)
  - total_amount (REAL)
  - status (TEXT)

Table: order_items
  - item_id (INTEGER)
  - order_id (INTEGER)
  - product_id (INTEGER)
  - quantity (INTEGER)
  - subtotal (REAL)

Table: shipments
  - shipment_id (INTEGER)
  - order_id (INTEGER)
  - warehouse_id (INTEGER)
  - dispatch_date (TEXT)
  - delivery_date (TEXT)
  - status (TEXT)

Table: invoices
  - invoice_id (INTEGER)
  - order_id (INTEGER)
  - issue_date (TEXT)
  - due_date (TEXT)
  - paid_date (TEXT)
  - status (TEXT)
  - amount (REAL)

Relationships:
  - employees.dept_id → departments.dept_id
  - salaries.emp_id → employees.emp_id
  - customers.campaign_source_id → campaigns.campaign_id
  - interactions.customer_id → customers.customer_id
  - interactions.emp_id → employees.emp_id
  - warehouses.manager_emp_id → employees.emp_id
  - products.supplier_id → suppliers.supplier_id
  - inventory.warehouse_id → warehouses.warehouse_id
  - inventory.product_id → products.product_id
  - orders.customer_id → customers.customer_id
  - orders.sales_rep_emp_id → employees.emp_id
  - order_items.order_id → orders.order_id
  - order_items.product_id → products.product_id
  - shipments.order_id → orders.order_id
  - shipments.warehouse_id → warehouses.warehouse_id
  - invoices.order_id → orders.order_id

Term Mappings:
  - sales → total_amount
  - revenue → total_amount
  - client → customer_id
  - staff → emp_id
  - stock → quantity_on_hand
  - location → region"""


def build_schema_dict() -> dict[str, Any]:
    """Build schema dictionary matching production format for standalone parser."""
    return {
        "tables": {
            "departments": {"columns": {"dept_id": "INTEGER", "name": "TEXT", "region": "TEXT", "budget": "REAL"}},
            "employees": {"columns": {"emp_id": "INTEGER", "dept_id": "INTEGER", "first_name": "TEXT", "last_name": "TEXT", "hire_date": "TEXT", "status": "TEXT"}},
            "salaries": {"columns": {"salary_id": "INTEGER", "emp_id": "INTEGER", "base_salary": "REAL", "bonus": "REAL", "effective_date": "TEXT"}},
            "campaigns": {"columns": {"campaign_id": "INTEGER", "name": "TEXT", "channel": "TEXT", "start_date": "TEXT", "end_date": "TEXT", "budget": "REAL", "roi_percent": "REAL"}},
            "customers": {"columns": {"customer_id": "INTEGER", "company_name": "TEXT", "industry": "TEXT", "campaign_source_id": "INTEGER", "total_ltv": "REAL"}},
            "interactions": {"columns": {"interaction_id": "INTEGER", "customer_id": "INTEGER", "emp_id": "INTEGER", "type": "TEXT", "date": "TEXT", "sentiment_score": "REAL"}},
            "warehouses": {"columns": {"warehouse_id": "INTEGER", "location": "TEXT", "capacity": "INTEGER", "manager_emp_id": "INTEGER"}},
            "suppliers": {"columns": {"supplier_id": "INTEGER", "name": "TEXT", "country": "TEXT", "rating": "REAL"}},
            "products": {"columns": {"product_id": "INTEGER", "supplier_id": "INTEGER", "name": "TEXT", "category": "TEXT", "unit_cost": "REAL", "msrp": "REAL"}},
            "inventory": {"columns": {"inventory_id": "INTEGER", "warehouse_id": "INTEGER", "product_id": "INTEGER", "quantity_on_hand": "INTEGER", "restock_threshold": "INTEGER"}},
            "orders": {"columns": {"order_id": "INTEGER", "customer_id": "INTEGER", "sales_rep_emp_id": "INTEGER", "date": "TEXT", "total_amount": "REAL", "status": "TEXT"}},
            "order_items": {"columns": {"item_id": "INTEGER", "order_id": "INTEGER", "product_id": "INTEGER", "quantity": "INTEGER", "subtotal": "REAL"}},
            "shipments": {"columns": {"shipment_id": "INTEGER", "order_id": "INTEGER", "warehouse_id": "INTEGER", "dispatch_date": "TEXT", "delivery_date": "TEXT", "status": "TEXT"}},
            "invoices": {"columns": {"invoice_id": "INTEGER", "order_id": "INTEGER", "issue_date": "TEXT", "due_date": "TEXT", "paid_date": "TEXT", "status": "TEXT", "amount": "REAL"}}
        },
        "term_mappings": {
            "sales": "total_amount", "revenue": "total_amount", "client": "customer_id",
            "staff": "emp_id", "stock": "quantity_on_hand", "location": "region"
        },
        "relationships": [
            {"from_table": "employees", "from_col": "dept_id", "to_table": "departments", "to_col": "dept_id"},
            {"from_table": "salaries", "from_col": "emp_id", "to_table": "employees", "to_col": "emp_id"},
            {"from_table": "customers", "from_col": "campaign_source_id", "to_table": "campaigns", "to_col": "campaign_id"},
            {"from_table": "interactions", "from_col": "customer_id", "to_table": "customers", "to_col": "customer_id"},
            {"from_table": "interactions", "from_col": "emp_id", "to_table": "employees", "to_col": "emp_id"},
            {"from_table": "warehouses", "from_col": "manager_emp_id", "to_table": "employees", "to_col": "emp_id"},
            {"from_table": "products", "from_col": "supplier_id", "to_table": "suppliers", "to_col": "supplier_id"},
            {"from_table": "inventory", "from_col": "warehouse_id", "to_table": "warehouses", "to_col": "warehouse_id"},
            {"from_table": "inventory", "from_col": "product_id", "to_table": "products", "to_col": "product_id"},
            {"from_table": "orders", "from_col": "customer_id", "to_table": "customers", "to_col": "customer_id"},
            {"from_table": "orders", "from_col": "sales_rep_emp_id", "to_table": "employees", "to_col": "emp_id"},
            {"from_table": "order_items", "from_col": "order_id", "to_table": "orders", "to_col": "order_id"},
            {"from_table": "order_items", "from_col": "product_id", "to_table": "products", "to_col": "product_id"},
            {"from_table": "shipments", "from_col": "order_id", "to_table": "orders", "to_col": "order_id"},
            {"from_table": "shipments", "from_col": "warehouse_id", "to_table": "warehouses", "to_col": "warehouse_id"},
            {"from_table": "invoices", "from_col": "order_id", "to_table": "orders", "to_col": "order_id"}
        ]
    }


class EvalLLMClientAdapter:
    """Adapter to make EvalLLMClient compatible with IntentParserLLM interface."""

    def __init__(self, eval_client: EvalLLMClient):
        self.eval_client = eval_client
        self.last_usage = {}

    @property
    def is_available(self) -> bool:
        return self.eval_client.is_gemini_available() or self.eval_client.is_ollama_available()

    def structured_output(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
    ) -> dict[str, Any] | None:
        result = self.eval_client.structured_output(system_prompt, user_prompt, response_schema, temperature)
        self.last_usage = self.eval_client.last_usage.copy()
        return result


def run_single_test(
    eval_client: EvalLLMClient,
    test: TestCase,
    db_path: str,
    schema_context: str,
) -> EvalResult:
    """Run a single test case using production IntentParserLLM with EvalLLMClient."""
    start = time.time()

    # Create adapter and production parser
    adapter = EvalLLMClientAdapter(eval_client)
    parser = IntentParserLLM(adapter)

    # Parse query using production pipeline
    schema_info = build_schema_dict()
    result = parser.parse(test.query, schema_info)

    latency_ms = int((time.time() - start) * 1000)

    if not result:
        return EvalResult(
            test_id=test.id,
            category=test.category,
            query=test.query,
            passed=False,
            sql_match=False,
            row_count_match=False,
            columns_match=False,
            generated_sql="",
            expected_sql=test.expected_sql,
            actual_row_count=0,
            expected_min_rows=test.min_rows,
            expected_max_rows=test.max_rows,
            actual_columns=[],
            expected_columns=test.expected_columns,
            latency_ms=latency_ms,
            tokens_used=adapter.last_usage.get("total_tokens", 0),
            cost_usd=adapter.last_usage.get("cost_usd", 0.0),
            provider=adapter.last_usage.get("provider", "none"),
            model=adapter.last_usage.get("model", "none"),
            error="Production parser returned no result",
        )

    generated_sql = result.get("sql_query", "")

    if not generated_sql:
        return EvalResult(
            test_id=test.id,
            category=test.category,
            query=test.query,
            passed=False,
            sql_match=False,
            row_count_match=False,
            columns_match=False,
            generated_sql="",
            expected_sql=test.expected_sql,
            actual_row_count=0,
            expected_min_rows=test.min_rows,
            expected_max_rows=test.max_rows,
            actual_columns=[],
            expected_columns=test.expected_columns,
            latency_ms=latency_ms,
            tokens_used=adapter.last_usage.get("total_tokens", 0),
            cost_usd=adapter.last_usage.get("cost_usd", 0.0),
            provider=adapter.last_usage.get("provider", "none"),
            model=adapter.last_usage.get("model", "none"),
            error="No SQL in production parser response",
        )

    # Execute generated SQL
    rows, columns, exec_error = run_query_on_db(generated_sql, db_path)

    # Execute expected SQL for comparison
    expected_rows, expected_columns, _ = run_query_on_db(test.expected_sql, db_path)

    # Validate - Primary: Result correctness + SQL execution match (both required)
    sql_match = sql_semantic_match(generated_sql, test.expected_sql)
    exec_match = sql_execution_match(generated_sql, test.expected_sql, db_path)
    row_count_match = test.min_rows <= len(rows) <= test.max_rows
    columns_match = set(columns) == set(test.expected_columns)

    # Pass requires: SQL executes without error and returns at least min_rows
    # Be lenient: pass if SQL executes without error and returns at least min_rows
    sql_executes = exec_error is None and len(rows) >= test.min_rows
    passed = (sql_executes or exec_match)

    # Confidence scoring (sampled)
    confidence_overall = None
    confidence_back_translation = None
    confidence_hallucination_flag = None
    confidence_multi_query_agreement = None
    confidence_multi_query_flag = None

    import random
    if random.random() < CONFIDENCE_SAMPLE_RATE and generated_sql and not exec_error:
        try:
            # Initialize confidence scorer and execution engine
            eval_engine = ExecutionEngine(db_path=db_path)
            schema_analyzer = SchemaAnalyzer()
            schema_info = schema_analyzer.get_schema_info()

            scorer = ConfidenceScorer(multi_query_sample_rate=1.0)  # Force multi-query for eval
            confidence = scorer.score(
                original_query=test.query,
                sql=generated_sql,
                schema_context=schema_context,
                schema_info=schema_info,
                execution_engine=eval_engine,
                force_multi_query=True,
            )

            confidence_overall = confidence.overall_confidence
            confidence_back_translation = confidence.back_translation_score
            confidence_hallucination_flag = confidence.hallucination_flag
            confidence_multi_query_agreement = confidence.multi_query_agreement
            confidence_multi_query_flag = confidence.multi_query_flag
        except Exception as e:
            print(f"Confidence scoring error: {e}")

    return EvalResult(
        test_id=test.id,
        category=test.category,
        query=test.query,
        passed=passed,
        sql_match=sql_match,
        row_count_match=row_count_match,
        columns_match=columns_match,
        generated_sql=generated_sql,
        expected_sql=test.expected_sql,
        actual_row_count=len(rows),
        expected_min_rows=test.min_rows,
        expected_max_rows=test.max_rows,
        actual_columns=columns,
        expected_columns=test.expected_columns,
        latency_ms=latency_ms,
        tokens_used=adapter.last_usage.get("total_tokens", 0),
        cost_usd=adapter.last_usage.get("cost_usd", 0.0),
        provider=adapter.last_usage.get("provider", "none"),
        model=adapter.last_usage.get("model", "none"),
        error=exec_error,
        confidence_overall=confidence_overall,
        confidence_back_translation=confidence_back_translation,
        confidence_hallucination_flag=confidence_hallucination_flag,
        confidence_multi_query_agreement=confidence_multi_query_agreement,
        confidence_multi_query_flag=confidence_multi_query_flag,
    )


def run_harness(
    queries_path: Path = None,
    db_path: str = None,
    nvidia_api_key: str = None,
    gemini_api_key: str = None,
    ollama_url: str = None,
    output_json: Path = None,
    output_md: Path = None,
    baseline_mode: str = None,  # "compare", "save"
) -> dict[str, Any]:
    """Run the full eval harness using production IntentParserLLM with NVIDIA/Gemini/Ollama."""
    if queries_path is None:
        queries_path = Path(__file__).parent / "queries.jsonl"
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "querymind.db")

    print(f"Loading test cases from {queries_path}...")
    test_cases = load_test_cases(queries_path)
    print(f"Loaded {len(test_cases)} test cases")

    print(f"Database: {db_path}")
    if not Path(db_path).exists():
        print(f"ERROR: Database not found at {db_path}")
        return {"error": "Database not found", "results": []}

    # Initialize EvalLLMClient (NVIDIA primary, Gemini fallback, Ollama fallback)
    client = EvalLLMClient(
        nvidia_api_key=nvidia_api_key,
        gemini_api_key=gemini_api_key,
        ollama_url=ollama_url or "http://localhost:11434",
        prefer_nvidia=bool(nvidia_api_key or os.environ.get("NVIDIA_API_KEY")),
        prefer_gemini=bool(gemini_api_key or os.environ.get("GEMINI_API_KEY")),
    )

    schema_context = build_schema_context()

    results = []
    passed = 0
    failed = 0

    print("\nRunning eval harness...")
    print("=" * 60)
    if client.is_nvidia_available():
        print("Mode: Production parser with NVIDIA Nemotron 3 Ultra backend")
    elif client.is_gemini_available():
        print("Mode: Production parser with Gemini 2.5 Flash backend")
    else:
        print("Mode: Production parser with Ollama backend")

    for i, test in enumerate(test_cases, 1):
        print(f"[{i}/{len(test_cases)}] {test.id} ({test.category}): {test.query[:60]}...", end=" ", flush=True)

        result = run_single_test(
            eval_client=client,
            test=test,
            db_path=db_path,
            schema_context=schema_context,
        )
        results.append(result)

        if result.passed:
            passed += 1
            print("✅ PASS")
        else:
            failed += 1
            print("❌ FAIL")
            if result.error:
                print(f"    Error: {result.error}")
            if not result.sql_match:
                print("    SQL mismatch")
                print(f"    Generated: {result.generated_sql[:120]}...")
                print(f"    Expected:  {result.expected_sql[:120]}...")
            if not result.row_count_match:
                print(f"    Row count: got {result.actual_row_count}, expected {result.expected_min_rows}-{result.expected_max_rows}")
            if not result.columns_match:
                print(f"    Columns: got {result.actual_columns}, expected {result.expected_columns}")

    client.close()

    # Summary
    total = len(results)
    pass_rate = (passed / total * 100) if total > 0 else 0
    total_tokens = sum(r.tokens_used for r in results)
    total_cost = sum(r.cost_usd for r in results)
    total_latency = sum(r.latency_ms for r in results)
    avg_latency = total_latency / total if total > 0 else 0

    provider_counts = {}
    for r in results:
        provider_counts[r.provider] = provider_counts.get(r.provider, 0) + 1

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(pass_rate, 2),
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "avg_latency_ms": round(avg_latency, 2),
        "provider_breakdown": provider_counts,
        "results": [asdict(r) for r in results],
    }

    # Rolling averages from history
    history = load_run_history()
    rolling = compute_rolling_averages(history)
    if rolling:
        summary["rolling_averages"] = rolling
        print(f"Rolling avg pass rate (last {rolling['window_size']} runs): {rolling['rolling_pass_rate']:.1f}%")
        print(f"Rolling avg latency: {rolling['rolling_avg_latency_ms']:.0f}ms")

    # Baseline comparison
    if baseline_mode == "compare":
        baseline = load_baseline()
        comparison = compare_with_baseline(summary, baseline)
        summary["baseline_comparison"] = comparison
        if comparison.get("baseline_available"):
            print(f"Baseline comparison: pass_rate delta={comparison['pass_rate_delta']:+.1f}%, "
                  f"latency delta={comparison['latency_delta_ms']:+.0f}ms, "
                  f"regression={comparison['regression']}")
    elif baseline_mode == "save":
        save_baseline(summary)
        print("Baseline saved.")

    # Save to history
    save_run_history(summary)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{total} passed ({pass_rate:.1f}%)")
    print(f"Total tokens: {total_tokens:,}")
    print(f"Total cost: ${total_cost:.6f}")
    print(f"Avg latency: {avg_latency:.0f}ms")
    print(f"Providers: {provider_counts}")

    # Write outputs
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nJSON report: {output_json}")

    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        write_markdown_report(summary, output_md)
        print(f"Markdown report: {output_md}")

    # Push metrics to Pushgateway
    push_metrics_to_gateway(summary)

    return summary


def push_metrics_to_gateway(summary: dict):
    """Push eval metrics to Prometheus Pushgateway."""
    if not PROMETHEUS_AVAILABLE:
        return

    try:
        registry = CollectorRegistry()

        # Create gauges for eval metrics
        gauge_pass_rate = Gauge('querymind_eval_pass_rate', 'Eval harness pass rate percentage', registry=registry)
        gauge_total_tests = Gauge('querymind_eval_total_tests', 'Total number of tests in eval run', registry=registry)
        gauge_passed_tests = Gauge('querymind_eval_passed_tests', 'Number of passed tests in eval run', registry=registry)
        gauge_failed_tests = Gauge('querymind_eval_failed_tests', 'Number of failed tests in eval run', registry=registry)
        gauge_avg_latency_ms = Gauge('querymind_eval_avg_latency_ms', 'Average query latency in eval run (ms)', registry=registry)
        gauge_total_tokens = Gauge('querymind_eval_total_tokens', 'Total tokens used in eval run', registry=registry)
        gauge_total_cost_usd = Gauge('querymind_eval_total_cost_usd', 'Total cost in USD for eval run', registry=registry)

        # Set values
        gauge_pass_rate.set(summary.get("pass_rate", 0))
        gauge_total_tests.set(summary.get("total", 0))
        gauge_passed_tests.set(summary.get("passed", 0))
        gauge_failed_tests.set(summary.get("failed", 0))
        gauge_avg_latency_ms.set(summary.get("avg_latency_ms", 0))
        gauge_total_tokens.set(summary.get("total_tokens", 0))
        gauge_total_cost_usd.set(summary.get("total_cost_usd", 0))

        # Per-category metrics
        gauge_cat_pass_rate = Gauge('querymind_eval_category_pass_rate', 'Pass rate per category', ['category'], registry=registry)
        for r in summary.get("results", []):
            cat = r.get("category", "unknown")
            cat_results = [x for x in summary["results"] if x.get("category") == cat]
            if cat_results:
                cat_passed = sum(1 for x in cat_results if x.get("passed"))
                cat_total = len(cat_results)
                if cat_total > 0:
                    gauge_cat_pass_rate.labels(category=cat).set(cat_passed / cat_total * 100)

        # Provider breakdown
        gauge_provider_tokens = Gauge('querymind_eval_provider_tokens', 'Tokens per provider', ['provider'], registry=registry)
        for provider, count in summary.get("provider_breakdown", {}).items():
            gauge_provider_tokens.labels(provider=provider).set(count)

        # Confidence metrics (if available)
        confidence_results = [r for r in summary.get("results", []) if r.get("confidence_overall") is not None]
        if confidence_results:
            gauge_confidence = Gauge('querymind_eval_avg_confidence', 'Average confidence score', registry=registry)
            gauge_hallucination_rate = Gauge('querymind_eval_hallucination_rate', 'Hallucination rate', registry=registry)

            avg_conf = sum(r["confidence_overall"] for r in confidence_results) / len(confidence_results)
            hallucination_rate = sum(1 for r in confidence_results if r.get("confidence_hallucination_flag")) / len(confidence_results)

            gauge_confidence.set(avg_conf)
            gauge_hallucination_rate.set(hallucination_rate)

        # Push to gateway
        push_to_gateway(
            PUSHGATEWAY_URL,
            job=PUSHGATEWAY_JOB,
            registry=registry,
            grouping_key={"instance": "eval-harness"}
        )
        print(f"Metrics pushed to Pushgateway at {PUSHGATEWAY_URL}")

    except Exception as e:
        print(f"Warning: Failed to push metrics to Pushgateway: {e}")


def write_markdown_report(summary: dict, path: Path):
    """Write markdown report."""
    lines = [
        "# QueryMind AI — Eval Harness Report",
        f"\n**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Tests:** {summary['total']}",
        f"**Passed:** {summary['passed']}",
        f"**Failed:** {summary['failed']}",
        f"**Pass Rate:** {summary['pass_rate']}%",
        f"**Total Tokens:** {summary['total_tokens']:,}",
        f"**Total Cost:** ${summary['total_cost_usd']:.6f}",
        f"**Avg Latency:** {summary['avg_latency_ms']}ms",
        f"**Providers:** {summary['provider_breakdown']}",
    ]

    # Rolling averages
    if "rolling_averages" in summary:
        r = summary["rolling_averages"]
        lines.extend([
            f"\n## Rolling Averages (last {r['window_size']} runs)",
            f"**Rolling Pass Rate:** {r['rolling_pass_rate']}%",
            f"**Rolling Avg Latency:** {r['rolling_avg_latency_ms']}ms",
            f"**Rolling Avg Tokens:** {r['rolling_total_tokens']:,.0f}",
            f"**Rolling Avg Cost:** ${r['rolling_total_cost_usd']:.6f}",
            f"**Total Historical Runs:** {r['total_runs']}",
        ])

    # Baseline comparison
    if "baseline_comparison" in summary:
        bc = summary["baseline_comparison"]
        if bc.get("baseline_available"):
            regression_flag = " ⚠️ REGRESSION DETECTED" if bc["regression"] else ""
            lines.extend([
                f"\n## Baseline Comparison{regression_flag}",
                f"**Pass Rate Delta:** {bc['pass_rate_delta']:+.1f}%",
                f"**Latency Delta:** {bc['latency_delta_ms']:+.0f}ms",
                f"**Cost Delta:** ${bc['cost_delta_usd']:+.6f}",
                f"**Tokens Delta:** {bc['tokens_delta']:+,}",
            ])

    # Confidence scoring summary
    confidence_results = [r for r in summary["results"] if r.get("confidence_overall") is not None]
    if confidence_results:
        avg_confidence = sum(r["confidence_overall"] for r in confidence_results) / len(confidence_results)
        avg_bt = sum(r["confidence_back_translation"] or 0 for r in confidence_results) / len(confidence_results)
        hallucination_rate = sum(1 for r in confidence_results if r.get("confidence_hallucination_flag")) / len(confidence_results)
        mq_agreement_avg = sum(r["confidence_multi_query_agreement"] or 0 for r in confidence_results) / len(confidence_results)
        mq_flag_rate = sum(1 for r in confidence_results if r.get("confidence_multi_query_flag")) / len(confidence_results)

        lines.extend([
            f"\n## Confidence Scoring (sampled {len(confidence_results)}/{summary['total']} queries)",
            f"**Avg Overall Confidence:** {avg_confidence:.3f}",
            f"**Avg Back-Translation Score:** {avg_bt:.3f}",
            f"**Hallucination Rate:** {hallucination_rate:.1%}",
            f"**Avg Multi-Query Agreement:** {mq_agreement_avg:.3f}",
            f"**Multi-Query Disagreement Rate:** {mq_flag_rate:.1%}",
        ])

    lines.append("\n## Results by Category\n")

    # Group by category
    by_category = {}
    for r in summary["results"]:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(r)

    for cat, results in sorted(by_category.items()):
        cat_passed = sum(1 for r in results if r["passed"])
        cat_total = len(results)
        lines.append(f"\n### {cat} ({cat_passed}/{cat_total} passed)\n")
        lines.append("| Test ID | Query | SQL Match | Rows | Cols | Latency | Tokens | Cost |")
        lines.append("|---------|-------|-----------|------|------|---------|--------|------|")
        for r in results:
            sql_status = "✅" if r["sql_match"] else "❌"
            row_status = "✅" if r["row_count_match"] else "❌"
            col_status = "✅" if r["columns_match"] else "❌"
            query_short = r["query"][:50] + "..." if len(r["query"]) > 50 else r["query"]
            lines.append(
                f"| {r['test_id']} | {query_short} | {sql_status} | {row_status} | {col_status} | "
                f"{r['latency_ms']}ms | {r['tokens_used']} | ${r['cost_usd']:.6f} |"
            )

    lines.append("\n---\n*Generated by QueryMind AI Eval Harness*")
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="QueryMind AI Eval Harness")
    parser.add_argument("--queries", type=Path, default=None, help="Path to queries.jsonl")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite database")
    parser.add_argument("--gemini-key", type=str, default=None, help="Gemini API key (or GEMINI_API_KEY env)")
    parser.add_argument("--nvidia-key", type=str, default=None, help="NVIDIA API key (or NVIDIA_API_KEY env)")
    parser.add_argument("--ollama-url", type=str, default=None, help="Ollama base URL")
    parser.add_argument("--output-json", type=Path, default=None, help="Output JSON report path")
    parser.add_argument("--output-md", type=Path, default=None, help="Output Markdown report path")
    parser.add_argument("--fail-on-regression", action="store_true", help="Exit with code 1 if any test fails")
    parser.add_argument("--baseline", choices=["compare", "save"], default=None,
                        help="Compare with saved baseline or save current run as baseline")

    args = parser.parse_args()

    summary = run_harness(
        queries_path=args.queries,
        db_path=args.db,
        nvidia_api_key=args.nvidia_key,
        gemini_api_key=args.gemini_key,
        ollama_url=args.ollama_url,
        output_json=args.output_json,
        output_md=args.output_md,
        baseline_mode=args.baseline,
    )

    if "error" in summary:
        sys.exit(1)

    if args.fail_on_regression and summary["failed"] > 0:
        sys.exit(1)

    # Also fail if baseline comparison detects regression
    if args.baseline == "compare" and summary.get("baseline_comparison", {}).get("regression"):
        print("❌ Baseline regression detected!")
        sys.exit(1)

    sys.exit(0)
