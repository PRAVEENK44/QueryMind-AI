"""Confidence Scoring - Hallucination detection and multi-query validation."""

from dataclasses import dataclass

from src.llm.client import LLMClient, get_llm_client


@dataclass
class ConfidenceResult:
    """Result of confidence scoring."""

    back_translation_score: float  # 0-1, similarity between original and back-translated query
    back_translated_question: str  # What the LLM thinks the SQL answers
    hallucination_flag: bool  # True if back-translation diverges significantly
    multi_query_agreement: float | None = None  # 0-1, result similarity between variants
    multi_query_flag: bool | None = None  # True if variants disagree
    variant_results: list | None = None  # Results from each variant
    overall_confidence: float = 0.0  # Combined confidence score


class ConfidenceScorer:
    """Scores confidence of generated SQL using back-translation and multi-query validation."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        back_translation_threshold: float = 0.7,
        multi_query_sample_rate: float = 0.1,  # 10% of queries get multi-query validation
    ):
        self.llm = llm_client or get_llm_client()
        self.back_translation_threshold = back_translation_threshold
        self.multi_query_sample_rate = multi_query_sample_rate
        self._import_sentence_transformer()

    def _import_sentence_transformer(self):
        """Lazy import sentence-transformer for embeddings."""
        self._embedder = None
        self._has_embedder = False
        try:
            # Suppress TF warnings
            import os

            os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
            os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            self._has_embedder = True
        except Exception as e:
            # Fallback to word overlap similarity
            self._embedder = None
            self._has_embedder = False
            print(f"SentenceTransformer not available, using fallback: {e}")

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """Compute semantic similarity between two texts."""
        if not self._has_embedder or not self._embedder:
            # Fallback: simple word overlap
            words1 = set(text1.lower().split())
            words2 = set(text2.lower().split())
            if not words1 or not words2:
                return 0.0
            intersection = words1 & words2
            union = words1 | words2
            return len(intersection) / len(union)

        embeddings = self._embedder.encode([text1, text2])
        # Cosine similarity
        import numpy as np

        sim = np.dot(embeddings[0], embeddings[1]) / (
            np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
        )
        return float(sim)

    def back_translate(self, sql: str, schema_context: str) -> str:
        """Ask LLM what question the SQL answers."""
        if not self.llm or not self.llm.is_available:
            return "LLM unavailable for back-translation"

        system_prompt = f"""You are a SQL expert. Given a SQL query and database schema,
describe in natural language what question this SQL answers. Be specific and accurate.

Database Schema:
{schema_context}

Output ONLY the natural language question, no explanations."""

        user_prompt = f"SQL Query:\n{sql}\n\nWhat question does this SQL answer?"

        response = self.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )

        return response or "Failed to generate back-translation"

    def check_hallucination(
        self, original_query: str, sql: str, schema_context: str
    ) -> tuple[float, str, bool]:
        """Check for hallucination via back-translation.

        Returns:
            Tuple of (similarity_score, back_translated_question, hallucination_flag)
        """
        back_translated = self.back_translate(sql, schema_context)
        similarity = self._compute_similarity(original_query, back_translated)
        hallucination_flag = similarity < self.back_translation_threshold
        return similarity, back_translated, hallucination_flag

    def generate_sql_variant(
        self, query: str, schema_info: dict, temperature: float = 0.3
    ) -> str | None:
        """Generate a SQL variant using the production parser with given temperature."""
        from evals.harness import build_schema_dict
        from src.llm.client import IntentParserLLM

        adapter = _EvalLLMClientAdapter(self.llm)
        parser = IntentParserLLM(adapter)
        schema_dict = build_schema_dict()

        result = parser.parse(query, schema_dict)
        if result and result.get("sql_query"):
            return result["sql_query"]
        return None

    def multi_query_validate(
        self, query: str, schema_info: dict, execution_engine, num_variants: int = 2
    ) -> tuple[float | None, bool | None, list]:
        """Generate multiple SQL variants and compare their results.

        Returns:
            Tuple of (agreement_score, disagreement_flag, variant_results)
        """
        variants = []
        temperatures = [0.2, 0.4, 0.6, 0.8][:num_variants]

        for temp in temperatures:
            sql = self.generate_sql_variant(query, schema_info, temperature=temp)
            if sql:
                variants.append((temp, sql))

        if len(variants) < 2:
            return None, None, []

        # Execute each variant
        results = []
        for temp, sql in variants:
            result = execution_engine.execute(sql)
            results.append(
                {
                    "temperature": temp,
                    "sql": sql,
                    "success": result.success,
                    "row_count": result.row_count,
                    "columns": result.columns,
                    "data": result.data if result.success else None,
                    "error": result.error,
                }
            )

        # Compare successful results
        successful = [r for r in results if r["success"]]
        if len(successful) < 2:
            return None, None, results

        # Compare row counts and column sets
        row_counts = [r["row_count"] for r in successful]
        column_sets = [set(r["columns"]) for r in successful]

        # Agreement: 1.0 if all row counts equal and column sets equal
        row_agreement = 1.0 if len(set(row_counts)) == 1 else 0.0
        col_agreement = 1.0 if len({frozenset(c) for c in column_sets}) == 1 else 0.0

        # For data comparison, sample first few rows
        data_agreement = 1.0
        if successful[0]["data"] and successful[1]["data"]:
            # Compare first min(5, len) rows
            sample_size = min(5, len(successful[0]["data"]), len(successful[1]["data"]))
            matches = 0
            for i in range(sample_size):
                if successful[0]["data"][i] == successful[1]["data"][i]:
                    matches += 1
            data_agreement = matches / sample_size if sample_size > 0 else 1.0

        agreement_score = (row_agreement + col_agreement + data_agreement) / 3
        disagreement_flag = agreement_score < 0.8

        return agreement_score, disagreement_flag, results

    def score(
        self,
        original_query: str,
        sql: str,
        schema_context: str,
        schema_info: dict,
        execution_engine,
        force_multi_query: bool = False,
    ) -> ConfidenceResult:
        """Run full confidence scoring pipeline."""
        # Back-translation hallucination check
        bt_score, bt_question, hallucination_flag = self.check_hallucination(
            original_query, sql, schema_context
        )

        # Multi-query validation (sampled or forced)
        mq_agreement = None
        mq_flag = None
        variant_results = None

        import random

        if force_multi_query or random.random() < self.multi_query_sample_rate:
            mq_agreement, mq_flag, variant_results = self.multi_query_validate(
                query=original_query, schema_info=schema_info, execution_engine=execution_engine
            )

        # Overall confidence: weighted combination
        # Back-translation is primary signal; multi-query is secondary
        if mq_agreement is not None:
            overall = 0.6 * bt_score + 0.4 * mq_agreement
        else:
            overall = bt_score

        # Heavy penalty for hallucination
        if hallucination_flag:
            overall *= 0.5

        # Heavy penalty for multi-query disagreement
        if mq_flag:
            overall *= 0.5

        return ConfidenceResult(
            back_translation_score=round(bt_score, 3),
            back_translated_question=bt_question,
            hallucination_flag=hallucination_flag,
            multi_query_agreement=round(mq_agreement, 3) if mq_agreement else None,
            multi_query_flag=mq_flag,
            variant_results=variant_results,
            overall_confidence=round(overall, 3),
        )


class _EvalLLMClientAdapter:
    """Adapter to make LLMClient compatible with IntentParserLLM interface."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.last_usage = {}

    @property
    def is_available(self) -> bool:
        return self.llm_client.is_available

    def structured_output(
        self, system_prompt: str, user_prompt: str, response_schema: dict, temperature: float = 0.2
    ) -> dict | None:
        result = self.llm_client.structured_output(
            system_prompt, user_prompt, response_schema, temperature
        )
        self.last_usage = getattr(self.llm_client, "last_usage", {}).copy()
        return result
