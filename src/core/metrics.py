"""Prometheus metrics for QueryMind AI."""

from prometheus_client import Counter, Gauge, Histogram, Info

# Query execution metrics
query_latency_seconds = Histogram(
    "querymind_query_latency_seconds",
    "Query execution latency in seconds",
    ["endpoint", "status"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

query_total = Counter(
    "querymind_query_total",
    "Total number of queries executed",
    ["endpoint", "status"]
)

# Token usage and cost metrics
query_tokens_total = Counter(
    "querymind_query_tokens_total",
    "Total tokens used for queries",
    ["provider", "model", "type"]  # type: prompt, completion, total
)

query_cost_usd_total = Counter(
    "querymind_query_cost_usd_total",
    "Total cost in USD for queries",
    ["provider", "model"]
)

# Error metrics
query_errors_total = Counter(
    "querymind_query_errors_total",
    "Total number of query errors",
    ["endpoint", "error_type"]
)

# Eval harness metrics
eval_accuracy = Gauge(
    "querymind_eval_accuracy",
    "Current eval harness pass rate (percentage)",
    ["run_id"]
)

eval_pass_rate = Gauge(
    "querymind_eval_pass_rate",
    "Eval harness pass rate percentage",
)

eval_total_tests = Gauge(
    "querymind_eval_total_tests",
    "Total number of tests in eval run",
)

eval_passed_tests = Gauge(
    "querymind_eval_passed_tests",
    "Number of passed tests in eval run",
)

eval_failed_tests = Gauge(
    "querymind_eval_failed_tests",
    "Number of failed tests in eval run",
)

eval_avg_latency_ms = Gauge(
    "querymind_eval_avg_latency_ms",
    "Average query latency in eval run (ms)",
)

eval_total_tokens = Gauge(
    "querymind_eval_total_tokens",
    "Total tokens used in eval run",
)

eval_total_cost_usd = Gauge(
    "querymind_eval_total_cost_usd",
    "Total cost in USD for eval run",
)

# Confidence scoring metrics
confidence_score = Histogram(
    "querymind_confidence_score",
    "Overall confidence score for queries",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

hallucination_detected_total = Counter(
    "querymind_hallucination_detected_total",
    "Total number of hallucinations detected via back-translation",
)

multi_query_disagreement_total = Counter(
    "querymind_multi_query_disagreement_total",
    "Total number of multi-query disagreements detected",
)

# System info
system_info = Info(
    "querymind_system",
    "QueryMind AI system information"
)

# Active connections (if using connection pool)
active_connections = Gauge(
    "querymind_active_connections",
    "Number of active database connections",
)


class MetricsRecorder:
    """Helper class to record metrics in a consistent way."""

    def __init__(self):
        self._initialized = False

    def init_system_info(self, version: str = "0.1.0", environment: str = "development"):
        """Initialize system info metric."""
        system_info.info({
            "version": version,
            "environment": environment,
            "service": "querymind-ai"
        })

    def record_query_latency(self, endpoint: str, latency_seconds: float, success: bool):
        """Record query latency."""
        status = "success" if success else "error"
        query_latency_seconds.labels(endpoint=endpoint, status=status).observe(latency_seconds)
        query_total.labels(endpoint=endpoint, status=status).inc()

    def record_tokens(self, provider: str, model: str, prompt_tokens: int, completion_tokens: int):
        """Record token usage."""
        query_tokens_total.labels(provider=provider, model=model, type="prompt").inc(prompt_tokens)
        query_tokens_total.labels(provider=provider, model=model, type="completion").inc(completion_tokens)
        query_tokens_total.labels(provider=provider, model=model, type="total").inc(prompt_tokens + completion_tokens)

    def record_cost(self, provider: str, model: str, cost_usd: float):
        """Record query cost."""
        if cost_usd > 0:
            query_cost_usd_total.labels(provider=provider, model=model).inc(cost_usd)

    def record_error(self, endpoint: str, error_type: str):
        """Record query error."""
        query_errors_total.labels(endpoint=endpoint, error_type=error_type).inc()

    def record_eval_results(self, run_id: str, results: dict):
        """Record eval harness results."""
        eval_pass_rate.set(results.get("pass_rate", 0))
        eval_total_tests.set(results.get("total", 0))
        eval_passed_tests.set(results.get("passed", 0))
        eval_failed_tests.set(results.get("failed", 0))
        eval_avg_latency_ms.set(results.get("avg_latency_ms", 0))
        eval_total_tokens.set(results.get("total_tokens", 0))
        eval_total_cost_usd.set(results.get("total_cost_usd", 0))

        if run_id:
            eval_accuracy.labels(run_id=run_id).set(results.get("pass_rate", 0))

    def record_confidence(self, overall_confidence: float):
        """Record confidence score."""
        confidence_score.observe(overall_confidence)

    def record_hallucination(self, detected: bool):
        """Record hallucination detection."""
        if detected:
            hallucination_detected_total.inc()

    def record_multi_query_disagreement(self, detected: bool):
        """Record multi-query disagreement."""
        if detected:
            multi_query_disagreement_total.inc()


# Global metrics recorder instance
metrics_recorder = MetricsRecorder()


def init_metrics(version: str = "0.1.0", environment: str = "development"):
    """Initialize metrics system."""
    metrics_recorder.init_system_info(version, environment)
    return metrics_recorder
