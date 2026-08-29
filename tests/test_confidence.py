"""Tests for confidence scoring (back-translation, multi-query validation)."""

from unittest.mock import Mock

import pytest

from src.core.confidence import ConfidenceResult, ConfidenceScorer
from src.core.execution_engine import ExecutionEngine, ExecutionResult


class TestConfidenceScorer:
    """Test confidence scoring components."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM client."""
        llm = Mock()
        llm.is_available = True
        llm.chat = Mock(return_value="This query shows average salary by department")
        llm.structured_output = Mock(return_value={"sql_query": "SELECT ..."})
        return llm

    @pytest.fixture
    def schema_context(self):
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
  - effective_date (TEXT)"""

    @pytest.fixture
    def schema_info(self):
        return {
            "tables": {
                "departments": {
                    "columns": {
                        "dept_id": "INTEGER",
                        "name": "TEXT",
                        "region": "TEXT",
                        "budget": "REAL",
                    }
                },
                "employees": {
                    "columns": {
                        "emp_id": "INTEGER",
                        "dept_id": "INTEGER",
                        "first_name": "TEXT",
                        "last_name": "TEXT",
                        "hire_date": "TEXT",
                        "status": "TEXT",
                    }
                },
                "salaries": {
                    "columns": {
                        "salary_id": "INTEGER",
                        "emp_id": "INTEGER",
                        "base_salary": "REAL",
                        "bonus": "REAL",
                        "effective_date": "TEXT",
                    }
                },
            },
            "relationships": [
                {
                    "from_table": "employees",
                    "from_col": "dept_id",
                    "to_table": "departments",
                    "to_col": "dept_id",
                },
                {
                    "from_table": "salaries",
                    "from_col": "emp_id",
                    "to_table": "employees",
                    "to_col": "emp_id",
                },
            ],
            "term_mappings": {},
        }

    @pytest.fixture
    def mock_execution_engine(self):
        """Create a mock execution engine."""
        engine = Mock(spec=ExecutionEngine)
        engine.execute = Mock(
            return_value=ExecutionResult(
                success=True,
                data=[{"department": "Engineering", "average_salary": 100000}],
                row_count=1,
                columns=["department", "average_salary"],
            )
        )
        return engine

    def test_back_translation_similar_query(self, mock_llm, schema_context):
        """Back-translation of matching query should have high similarity."""
        scorer = ConfidenceScorer(llm_client=mock_llm, back_translation_threshold=0.7)

        original = "Show average salary by department"
        sql = "SELECT d.name, AVG(s.base_salary) FROM departments d JOIN employees e ON d.dept_id = e.dept_id JOIN salaries s ON e.emp_id = s.emp_id GROUP BY d.name"

        similarity, back_translated, flag = scorer.check_hallucination(
            original, sql, schema_context
        )

        assert similarity > 0.5  # Should be reasonably similar
        assert flag is False  # Not a hallucination
        assert "salary" in back_translated.lower()
        assert "department" in back_translated.lower()

    def test_back_translation_divergent_query(self, mock_llm, schema_context):
        """Back-translation of divergent query should be flagged."""
        # Make LLM return something completely different
        mock_llm.chat = Mock(return_value="This query shows total budget by region")
        scorer = ConfidenceScorer(llm_client=mock_llm, back_translation_threshold=0.7)

        original = "Show average salary by department"
        sql = "SELECT d.region, SUM(d.budget) FROM departments d GROUP BY d.region"

        similarity, back_translated, flag = scorer.check_hallucination(
            original, sql, schema_context
        )

        assert similarity < 0.7  # Low similarity
        assert flag is True  # Hallucination detected

    def test_fallback_similarity_no_embedder(self, schema_context):
        """Word overlap similarity should work without sentence-transformers."""
        # Create scorer with embedder explicitly disabled
        scorer = ConfidenceScorer(
            llm_client=Mock(is_available=False), back_translation_threshold=0.7
        )
        # Force disable embedder
        scorer._has_embedder = False
        scorer._embedder = None

        # Test word overlap similarity
        text1 = "average salary by department"
        text2 = "average salary by department"
        sim = scorer._compute_similarity(text1, text2)
        assert sim == 1.0

        text1 = "average salary by department"
        text2 = "total budget by region"
        sim = scorer._compute_similarity(text1, text2)
        assert sim < 0.5  # Low overlap

    def test_multi_query_agreement_same_results(self, mock_llm, schema_info, mock_execution_engine):
        """Multiple variants returning same results should have high agreement."""
        # Mock generate_sql_variant to return different SQL but same results
        mock_llm.chat = Mock(
            side_effect=[
                "SELECT d.name, AVG(s.base_salary) FROM departments d JOIN employees e ON d.dept_id = e.dept_id JOIN salaries s ON e.emp_id = s.emp_id GROUP BY d.name",
                "SELECT department, AVG(salary) FROM dept JOIN emp ON dept.id = emp.dept_id JOIN sal ON emp.id = sal.emp_id GROUP BY department",
            ]
        )

        scorer = ConfidenceScorer(llm_client=mock_llm, multi_query_sample_rate=1.0)

        agreement, flag, variants = scorer.multi_query_validate(
            query="Show average salary by department",
            schema_info=schema_info,
            execution_engine=mock_execution_engine,
            num_variants=2,
        )

        assert agreement == 1.0  # Perfect agreement
        assert flag is False
        assert len(variants) == 2

    def test_multi_query_disagreement_different_results(
        self, mock_llm, schema_info, mock_execution_engine
    ):
        """Variants returning different results should be flagged."""
        # Mock engine to return different results for each call
        call_count = [0]

        def mock_execute(sql):
            call_count[0] += 1
            if call_count[0] == 1:
                return ExecutionResult(
                    success=True,
                    data=[{"dept": "Eng", "avg": 100}],
                    row_count=1,
                    columns=["dept", "avg"],
                )
            else:
                return ExecutionResult(
                    success=True,
                    data=[{"dept": "Sales", "avg": 80}],
                    row_count=1,
                    columns=["dept", "avg"],
                )

        mock_execution_engine.execute = mock_execute

        mock_llm.chat = Mock(
            side_effect=[
                "SELECT d.name, AVG(s.base_salary) FROM departments d JOIN employees e ON d.dept_id = e.dept_id JOIN salaries s ON e.emp_id = s.emp_id GROUP BY d.name",
                "SELECT d.region, SUM(d.budget) FROM departments d GROUP BY d.region",
            ]
        )

        scorer = ConfidenceScorer(llm_client=mock_llm, multi_query_sample_rate=1.0)

        agreement, flag, variants = scorer.multi_query_validate(
            query="Show average salary by department",
            schema_info=schema_info,
            execution_engine=mock_execution_engine,
            num_variants=2,
        )

        assert agreement < 1.0  # Disagreement
        assert flag is True  # Flagged

    def test_overall_confidence_combines_signals(
        self, mock_llm, schema_context, schema_info, mock_execution_engine
    ):
        """Overall confidence should combine back-translation and multi-query."""
        mock_llm.chat = Mock(
            side_effect=[
                "Show average salary by department",  # back-translation
                "SELECT d.name, AVG(s.base_salary) FROM departments d JOIN employees e ON d.dept_id = e.dept_id JOIN salaries s ON e.emp_id = s.emp_id GROUP BY d.name",  # variant 1
                "SELECT department, AVG(salary) FROM dept JOIN emp ON dept.id = emp.dept_id JOIN sal ON emp.id = sal.emp_id GROUP BY department",  # variant 2
            ]
        )

        scorer = ConfidenceScorer(llm_client=mock_llm, multi_query_sample_rate=1.0)

        result = scorer.score(
            original_query="Show average salary by department",
            sql="SELECT d.name, AVG(s.base_salary) FROM departments d JOIN employees e ON d.dept_id = e.dept_id JOIN salaries s ON e.emp_id = s.emp_id GROUP BY d.name",
            schema_context=schema_context,
            schema_info=schema_info,
            execution_engine=mock_execution_engine,
            force_multi_query=True,
        )

        assert isinstance(result, ConfidenceResult)
        assert 0 <= result.overall_confidence <= 1
        assert result.back_translation_score > 0.5
        assert result.multi_query_agreement == 1.0
        assert result.hallucination_flag is False
        assert result.multi_query_flag is False

    def test_hallucination_penalty(
        self, mock_llm, schema_context, schema_info, mock_execution_engine
    ):
        """Hallucination should heavily penalize overall confidence."""
        mock_llm.chat = Mock(
            side_effect=[
                "This query shows total budget by region",  # divergent back-translation
                "SELECT d.name, AVG(s.base_salary) FROM departments d JOIN employees e ON d.dept_id = e.dept_id JOIN salaries s ON e.emp_id = s.emp_id GROUP BY d.name",
                "SELECT department, AVG(salary) FROM dept JOIN emp ON dept.id = emp.dept_id JOIN sal ON emp.id = sal.emp_id GROUP BY department",
            ]
        )

        scorer = ConfidenceScorer(llm_client=mock_llm, multi_query_sample_rate=1.0)

        result = scorer.score(
            original_query="Show average salary by department",
            sql="SELECT d.region, SUM(d.budget) FROM departments d GROUP BY d.region",  # Wrong SQL
            schema_context=schema_context,
            schema_info=schema_info,
            execution_engine=mock_execution_engine,
            force_multi_query=True,
        )

        assert result.hallucination_flag is True
        assert result.overall_confidence < 0.5  # Heavily penalized

    def test_multi_query_disagreement_penalty(self, mock_llm, schema_context, schema_info):
        """Multi-query disagreement should penalize overall confidence."""
        # Engine that returns different results
        call_count = [0]

        def mock_execute(sql):
            call_count[0] += 1
            if call_count[0] == 1:
                return ExecutionResult(
                    success=True,
                    data=[{"dept": "Eng", "avg": 100}],
                    row_count=1,
                    columns=["dept", "avg"],
                )
            else:
                return ExecutionResult(
                    success=True,
                    data=[{"dept": "Sales", "avg": 80}],
                    row_count=1,
                    columns=["dept", "avg"],
                )

        engine = Mock(spec=ExecutionEngine)
        engine.execute = mock_execute

        mock_llm.chat = Mock(
            side_effect=[
                "Show average salary by department",  # back-translation (good)
                "SELECT d.name, AVG(s.base_salary) FROM departments d JOIN employees e ON d.dept_id = e.dept_id JOIN salaries s ON e.emp_id = s.emp_id GROUP BY d.name",
                "SELECT d.region, SUM(d.budget) FROM departments d GROUP BY d.region",
            ]
        )

        scorer = ConfidenceScorer(llm_client=mock_llm, multi_query_sample_rate=1.0)

        result = scorer.score(
            original_query="Show average salary by department",
            sql="SELECT d.name, AVG(s.base_salary) FROM departments d JOIN employees e ON d.dept_id = e.dept_id JOIN salaries s ON e.emp_id = s.emp_id GROUP BY d.name",
            schema_context=schema_context,
            schema_info=schema_info,
            execution_engine=engine,
            force_multi_query=True,
        )

        assert result.multi_query_flag is True
        assert result.overall_confidence < 0.5  # Heavily penalized


class TestConfidenceResult:
    """Test ConfidenceResult dataclass."""

    def test_dataclass_creation(self):
        result = ConfidenceResult(
            back_translation_score=0.8,
            back_translated_question="Show average salary by department",
            hallucination_flag=False,
            multi_query_agreement=0.9,
            multi_query_flag=False,
            variant_results=[],
            overall_confidence=0.85,
        )
        assert result.back_translation_score == 0.8
        assert result.overall_confidence == 0.85
        assert result.hallucination_flag is False
