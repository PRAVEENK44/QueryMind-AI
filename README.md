# QueryMind AI - Production-Ready NL-to-SQL Analytics Platform

[![CI](https://github.com/PRAVEENK44/QueryMind-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/PRAVEENK44/QueryMind-AI/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

QueryMind AI is a **production-grade, multi-agent Natural Language to SQL analytics platform** that transforms natural language questions into executable SQL queries, returning visualized results with AI-generated explanations. Built with enterprise requirements in mind: observability, security, evaluation, and Kubernetes deployment.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            QueryMind AI Pipeline                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │ IntentParser │───▶│ QueryValidator│───▶│QueryGenerator│───▶│Execution │  │
│  │     LLM      │    │  (Guardrails) │    │  (Compiler)  │    │ Engine   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────────┘  │
│         │                   │                   │                   │       │
│         ▼                   ▼                   ▼                   ▼       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │  Confidence  │    │  Back-trans- │    │ Multi-query  │    │  Viz &   │  │
│  │   Scoring    │    │  lation      │    │ Validation   │    │ Explainer│  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Components

| Component | Purpose |
|-----------|---------|
| **IntentParserLLM** | Converts NL → structured `QueryIntent` JSON using LLM with JSON schema enforcement |
| **QueryValidator** | AST-based guardrails (sqlglot) blocking DDL/DML, enforcing row limits, read-only enforcement |
| **QueryGenerator** | Compiles `QueryIntent` → parameterized SQL with proper JOINs |
| **ExecutionEngine** | Safe SQLite/PostgreSQL execution with connection pooling |
| **ConfidenceScorer** | Back-translation hallucination detection + multi-query variant validation |
| **VizGenerator** | Auto-selects chart type (bar/line/pie/area) based on result shape |
| **ExplanationGenerator** | Human-readable narratives with typewriter streaming |

---

## 🚀 Features

### Multi-Agent NL-to-SQL Pipeline
- **Structured Output**: JSON schema-enforced LLM responses (OpenAI, NVIDIA Nemotron, Gemini, Ollama)
- **Schema Grounding**: Dynamic schema context injection prevents hallucination
- **Fallback Chain**: NVIDIA Nemotron 3 Ultra → Gemini 2.5 Flash → Ollama (local)

### Runtime Guardrails & Security
- **sqlglot AST Validation**: Blocks `DROP`, `DELETE`, `UPDATE`, `INSERT`, `CREATE`, `ALTER`
- **Row Limits**: Hard cap (default 1000 rows) on all queries
- **Read-Only DB User**: PostgreSQL `querymind_ro` user with `SELECT` only privileges
- **API Key Auth**: `X-API-Key` header required for `/api/query` endpoint

### Confidence Scoring & Hallucination Detection
- **Back-Translation**: SQL → NL → SQL round-trip comparison (semantic equivalence)
- **Multi-Query Validation**: Generates 2-4 SQL variants, measures agreement
- **Overall Confidence**: Weighted score (0.0-1.0) exposed in API response & metrics

### Observability Stack
- **Prometheus Metrics**: Latency, tokens, cost, errors, eval pass rate, confidence, hallucinations
- **Grafana Dashboard**: 12-panel overview (latency, throughput, cost, confidence, errors)
- **Alertmanager**: 9 alert rules (high error rate, latency, cost spike, eval regression)
- **Pushgateway**: Batch job metrics (eval harness results)

### Evaluation Harness
- **30 Golden Queries** across 4 domains (HR, CRM, Supply Chain, Finance)
- **Semantic SQL Matching**: sqlglot-based structural comparison
- **Rolling Averages**: 10-run rolling pass rate with baseline regression detection
- **CI Integration**: Runs on every push with NVIDIA→Gemini→Ollama fallback

### Deployment
- **Multi-stage Dockerfile**: Non-root, read-only FS, health checks, multi-arch
- **Docker Compose**: 3 profiles (SQLite, PostgreSQL, Observability)
- **Kubernetes (Kustomize)**: Base + dev/staging/prod/kind overlays
- **kind Cluster**: Local development with port mappings
- **GitHub Actions CI**: Lint, typecheck, tests, eval, Docker build, SBOM, perf benchmarks

---

## 📋 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for containerized deployment)
- NVIDIA API key (for Nemotron 3 Ultra) or Gemini API key

### Local Development (SQLite)
```bash
# 1. Clone and enter
git clone https://github.com/PRAVEENK44/QueryMind-AI.git
cd QueryMind-AI

# 2. Set API key (required for production parser)
export NVIDIA_API_KEY="your-nvidia-key"  # or GEMINI_API_KEY

# 3. Start with Docker Compose (includes observability)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

# 4. Access services
# API:        http://localhost:8000
# Grafana:    http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
# Pushgateway: http://localhost:9091
```

### Local Development (PostgreSQL)
```bash
# Start with PostgreSQL backend
docker compose -f docker-compose.yml -f docker-compose.postgres.yml -f docker-compose.observability.yml up -d
```

### Bare Metal (Python)
```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export NVIDIA_API_KEY="your-key"

# Run API server
python api.py

# Run Streamlit UI (optional)
streamlit run app.py
```

---

## 🔐 Authentication

All `/api/query` requests require an API key:

```bash
curl -X POST http://localhost:8000/api/query \
  -H "X-API-Key: dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"query": "Show average salary by department"}'
```

**Default key**: `dev-key-change-in-production` (change in production via `API_KEY` env var)

---

## 📊 API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check with LLM provider status |
| `/api/query` | POST | Yes | Execute NL query, return SQL + results + viz |
| `/api/atlas` | GET | No | Database schema topology (Vis-Network) |
| `/api/dashboard` | GET | No | Auto-generated KPI dashboard |
| `/metrics` | GET | No | Prometheus metrics exposition |

### Query Response Format
```json
{
  "success": true,
  "explanation": "Human-readable analysis...",
  "visualization": { "data": [...], "layout": {...} },
  "data": { "results": [{...}] },
  "metadata": {
    "generated_sql": "SELECT ...",
    "usage": { "provider": "nvidia", "model": "...", "prompt_tokens": 1571, "completion_tokens": 450, "cost_usd": 0.000206 },
    "confidence": { "overall": 0.87, "back_translation_score": 0.92, "hallucination_flag": false }
  }
}
```

---

## 🧪 Evaluation Harness

```bash
# Run full eval suite (30 queries)
export NVIDIA_API_KEY="your-key"
python -m evals.harness --queries evals/queries.jsonl --db querymind.db

# With baseline comparison
python -m evals.harness --baseline compare --output-json eval-results.json

# Save new baseline
python -m evals.harness --baseline save
```

### Output
- **JSON Report**: Detailed per-query results, latency, tokens, cost, confidence
- **Markdown Report**: Human-readable summary with pass/fail table
- **Prometheus Pushgateway**: Metrics pushed for Grafana/Alertmanager

### Validation Criteria
1. **Result Correctness** (primary): Row count, columns, data match
2. **SQL Semantic Match** (secondary): AST structural equivalence

---

## 🐳 Docker Compose Profiles

| Profile | Command | Use Case |
|---------|---------|----------|
| **Default (SQLite)** | `docker compose up -d` | Quick local dev |
| **PostgreSQL** | `docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d` | Production-like |
| **Observability** | `docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d` | Full monitoring |
| **Full Stack** | `docker compose -f docker-compose.yml -f docker-compose.postgres.yml -f docker-compose.observability.yml up -d` | Complete stack |

---

## ☸️ Kubernetes Deployment

### kind (Local Development)
```bash
# Create cluster
kind create cluster --config kind-config.yaml

# Deploy
kubectl apply -k k8s/overlays/kind

# Access (port-forwards configured in kind-config.yaml)
# API:        http://localhost:8000
# Grafana:    http://localhost:3000
# Prometheus: http://localhost:9090
```

### Production (Kustomize)
```bash
# Deploy to production
kubectl apply -k k8s/overlays/prod

# Or staging/dev
kubectl apply -k k8s/overlays/staging
kubectl apply -k k8s/overlays/dev
```

### Key K8s Features
- **PostgreSQL StatefulSet** with init script creating `querymind_ro` read-only user
- **Prometheus annotations** for auto-scraping
- **Resource limits/requests** tuned per environment
- **Ingress** for production (NGINX)
- **Secrets** for API keys (never in configmaps)

---

## 📈 Grafana Dashboard

Pre-configured 12-panel dashboard at `http://localhost:3000`:

1. **Query Latency (p50/p95/p99)** - Histogram heatmap
2. **Query Throughput** - Requests/sec by status
3. **Token Usage** - Prompt/completion tokens by provider/model
4. **Token Cost Rate (USD/hr) — Tracked for Governance** - Cost tracking
5. **Error Rate** - By endpoint and error type
6. **Eval Pass Rate** - Rolling 10-run average
7. **Confidence Score Distribution** - Histogram
8. **Hallucination Detection Rate** - Counter
9. **Multi-Query Disagreement Rate** - Counter
10. **Active Connections** - Database pool
11. **System Info** - Version, environment
12. **LLM Provider Availability** - Status panel

---

## 🔔 Alerting Rules (Alertmanager)

| Alert | Condition | Severity |
|-------|-----------|----------|
| `HighErrorRate` | >5% errors over 5m | critical |
| `HighLatency` | p99 > 10s over 5m | warning |
| `CostSpike` | Cost rate > $1/hr | warning |
| `EvalRegression` | Pass rate < 80% | critical |
| `LowConfidence` | Avg confidence < 0.5 | warning |
| `HallucinationSpike` | >10 hallucinations/hr | warning |
| `LLMUnavailable` | Provider down > 1m | critical |
| `DBConnectionsHigh` | >80% pool used | warning |
| `PodRestartLoop` | Restarts > 5 in 10m | critical |

---

## 🔧 Configuration

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `NVIDIA_API_KEY` | - | NVIDIA Nemotron 3 Ultra API key |
| `GEMINI_API_KEY` | - | Google Gemini API key |
| `OPENAI_API_KEY` | - | OpenAI API key (fallback) |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Ollama model for local fallback |
| `API_KEY` | `dev-key-change-in-production` | API auth key |
| `DATABASE_URL` | `sqlite:///querymind.db` | Database connection |
| `ENVIRONMENT` | `development` | `development`/`staging`/`production` |
| `PUSHGATEWAY_URL` | `http://pushgateway:9091` | Prometheus Pushgateway |

### Key Files
- `docker-compose.yml` - Base services
- `docker-compose.observability.yml` - Prometheus/Grafana/Alertmanager/Pushgateway
- `docker-compose.postgres.yml` - PostgreSQL backend
- `prometheus/prometheus.yml` - Scrape config
- `prometheus/rules/querymind.yml` - Alerting rules
- `grafana/dashboards/querymind-overview.json` - Dashboard
- `grafana/provisioning/` - Auto-provisioning config
- `alertmanager/alertmanager.yml` - Notification routing

---

## 🗂️ Project Structure

```
QueryMind-AI/
├── .github/workflows/ci.yml          # GitHub Actions CI pipeline
├── alertmanager/alertmanager.yml     # Alert routing
├── api.py                            # FastAPI application entry point
├── app.py                            # Streamlit UI (optional)
├── docker-compose.yml                # Base services (API, Redis)
├── docker-compose.observability.yml  # Prometheus, Grafana, Alertmanager, Pushgateway
├── docker-compose.postgres.yml       # PostgreSQL backend
├── docker-compose.prod.yml           # Production overrides
├── Dockerfile                        # Multi-stage production image
├── Dockerfile.postgres               # PostgreSQL init image
├── kind-config.yaml                  # kind cluster config
├── k8s/                              # Kubernetes manifests (Kustomize)
│   ├── base/                         # Base resources
│   └── overlays/                     # Environment overlays (dev/staging/prod/kind)
├── mcp_server.py                     # MCP tool server
├── postgres_init.sql                 # PostgreSQL init (read-only user)
├── prometheus/                       # Prometheus config & rules
├── grafana/                          # Grafana dashboards & provisioning
├── evals/                            # Evaluation harness
│   ├── harness.py                    # Main eval runner
│   ├── client.py                     # Eval LLM client (NVIDIA/Gemini/Ollama)
│   ├── queries.jsonl                 # 30 golden queries
│   └── baseline.json                 # Baseline for regression detection
├── src/
│   ├── agents/                       # Schema analyzer, validator, grounder
│   ├── core/                         # Execution, confidence, viz, explanation
│   ├── llm/client.py                 # Unified LLM client (multi-provider)
│   └── database.py                   # SQLite bootstrap
├── tests/                            # Unit & integration tests
├── frontend/                         # Static UI (HTML/CSS/JS)
├── requirements.txt                  # Python dependencies
├── pyproject.toml                    # Project config (ruff, mypy, pytest)
├── Makefile                          # Common commands
├── DEPLOY_KIND.md                    # kind deployment guide
└── README.md                         # This file
```

---

## 🧰 Development

### Common Commands (Makefile)
```bash
make install          # Install dependencies
make test             # Run unit tests
make lint             # Run ruff
make typecheck        # Run mypy
make eval             # Run eval harness
make docker-build     # Build Docker image
make docker-up        # Start docker compose
make docker-down      # Stop docker compose
make kind-create      # Create kind cluster
make kind-deploy      # Deploy to kind
make clean            # Clean caches
```

### Running Tests
```bash
# Unit tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Eval harness (requires API key)
export NVIDIA_API_KEY="..."
python -m evals.harness
```

### Code Quality
```bash
# Lint
ruff check .

# Format
ruff format .

# Type check
mypy src/
```

---

## 📦 CI/CD Pipeline (GitHub Actions)

The `.github/workflows/ci.yml` runs on every push/PR:

1. **Lint & Format** - Ruff
2. **Type Check** - MyPy
3. **Unit Tests** - Pytest with coverage
4. **Eval Harness** - NVIDIA → Gemini → Ollama fallback
5. **Docker Build** - Multi-arch (amd64/arm64), Hadolint, SBOM (Syft)
6. **Performance Benchmarks** - On main branch only
7. **Deploy to kind** - Optional manual step

---

## 🔒 Security

- **No secrets in repo** - All keys via environment variables
- **Read-only DB user** - PostgreSQL `querymind_ro` with `SELECT` only
- **SQL injection prevention** - Parameterized queries, AST validation
- **Non-root containers** - Dockerfile uses `appuser` (UID 1000)
- **Read-only filesystem** - Container root FS mounted read-only
- **API key authentication** - Required for query execution

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes with tests
4. Run `make lint test typecheck eval`
5. Submit a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- **NVIDIA Nemotron 3 Ultra** - Primary LLM for production parsing
- **Google Gemini** - Fallback LLM
- **Ollama** - Local model runner
- **sqlglot** - SQL parsing and validation
- **FastAPI** - Modern Python web framework
- **Prometheus/Grafana/Alertmanager** - Observability stack

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/PRAVEENK44/QueryMind-AI/issues)
- **Discussions**: [GitHub Discussions](https://github.com/PRAVEENK44/QueryMind-AI/discussions)

---

**Built with ❤️ for production-grade NL-to-SQL analytics**