"""QueryMind AI - Nexus Backend (Total Isolation Edition v14)."""
import os
import time
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Depends, Security
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader

from pydantic import BaseModel
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.core.metrics import init_metrics, metrics_recorder

# ================= CORE INITIALIZATION =================
# We keep top-level imports ONLY for FastAPI/Pydantic/OS to ensure a sub-second network bind.
app = FastAPI(title="QueryMind AI Nexus API")

# Initialize Prometheus metrics
init_metrics(version="0.1.0", environment=os.environ.get("ENVIRONMENT", "development"))

# API Key authentication
API_KEY = os.environ.get("API_KEY", "dev-key-change-in-production")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Upload directory for user-provided databases
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# CORS configuration - restrict in production
origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)

# Mount frontend folders if they exist
for folder in ["css", "js"]:
    path = os.path.join(BASE_DIR, "frontend", folder)
    if os.path.exists(path):
        app.mount(f"/{folder}", StaticFiles(directory=path), name=folder)

# ================= CORE COMPONENTS (Global Lazy Handlers) =================
_core = {"initialized": False}
_custom_cores: dict[str, dict] = {}  # Per-session cores for uploaded databases

def get_core():
    """Lazily import and initialize everything. This is called ONLY when a user interacts."""
    if not _core.get("initialized"):
        # Local imports ensure the server starts even if libraries are heavy
        print("Nexus Brain: Lazy Wake-up triggered...", flush=True)
        from src.agents.schema_analyzer import SchemaAnalyzer
        from src.agents.validator import QueryValidator
        from src.core.execution_engine import ExecutionEngine
        from src.core.explanation_generator import ExplanationGenerator
        from src.core.query_generator import QueryGenerator
        from src.core.viz_generator import VizGenerator
        from src.database import init_database
        from src.llm.client import IntentParserLLM, get_llm_client

        try:
            init_database()
        except: pass

        llm_client = get_llm_client()
        _core["parser_llm"] = IntentParserLLM(llm_client)
        _core["query_generator"] = QueryGenerator()
        _core["execution_engine"] = ExecutionEngine()
        _core["viz_generator"] = VizGenerator()
        _core["explanation_generator"] = ExplanationGenerator()
        _core["schema_analyzer"] = SchemaAnalyzer()
        _core["validator"] = QueryValidator()
        _core["schema_info"] = _core["schema_analyzer"].get_schema_info()
        _core["initialized"] = True
        print("Nexus Brain: Fully Synchronized.", flush=True)
    return _core

def _extract_schema_from_db(engine) -> dict:
    """Auto-extract schema from any SQLite/SQL database using SQLAlchemy inspector."""
    from sqlalchemy import inspect as sa_inspect
    try:
        insp = sa_inspect(engine.engine)
        tables = {}
        relationships = []

        for table_name in insp.get_table_names():
            cols = {}
            for col in insp.get_columns(table_name):
                cols[col["name"]] = str(col["type"])

            # Auto-detect FK relationships
            for fk in insp.get_foreign_keys(table_name):
                if fk.get("constrained_columns") and fk.get("referred_columns"):
                    relationships.append({
                        "from_table": table_name,
                        "from_col": fk["constrained_columns"][0],
                        "to_table": fk["referred_table"],
                        "to_col": fk["referred_columns"][0],
                    })

            tables[table_name] = {
                "columns": cols,
                "description": f"User-uploaded table: {table_name}"
            }

        return {"tables": tables, "relationships": relationships, "term_mappings": {}}
    except Exception as e:
        print(f"Schema extraction error: {e}")
        return {"tables": {}, "relationships": [], "term_mappings": {}}

def get_custom_core(session_id: str, db_path: str) -> dict:
    """Get or create a lightweight per-session core for a user-uploaded database."""
    if session_id in _custom_cores:
        return _custom_cores[session_id]

    from src.agents.validator import QueryValidator
    from src.core.execution_engine import ExecutionEngine
    from src.core.explanation_generator import ExplanationGenerator
    from src.core.query_generator import QueryGenerator
    from src.core.viz_generator import VizGenerator
    from src.llm.client import IntentParserLLM, get_llm_client

    engine = ExecutionEngine(db_path=db_path)
    schema_info = _extract_schema_from_db(engine)
    llm_client = get_llm_client()

    _custom_cores[session_id] = {
        "execution_engine": engine,
        "schema_info": schema_info,
        "parser_llm": IntentParserLLM(llm_client),
        "query_generator": QueryGenerator(),
        "viz_generator": VizGenerator(),
        "explanation_generator": ExplanationGenerator(),
        "validator": QueryValidator(),
        "db_path": db_path,
        "initialized": True,
    }
    print(f"Custom DB core initialized for session {session_id}: {len(schema_info['tables'])} tables found.", flush=True)
    return _custom_cores[session_id]

# ================= UTILITIES =================
def force_primitive(v):
    """Recursively converts all values to JSON-safe primitives.
    Handles numpy arrays/scalars, Plotly bdata binary arrays, datetime, sets.
    """
    if v is None or isinstance(v, (bool, str)): return v
    if isinstance(v, float):
        import math
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, int): return v
    if hasattr(v, "isoformat"): return v.isoformat()
    # Decode Plotly binary-encoded arrays (plotly >= 6.x uses {'dtype': 'f8', 'bdata': '...'})
    if isinstance(v, dict) and "bdata" in v and "dtype" in v:
        import base64
        import struct
        DTYPE_MAP = {
            'f4': ('f', 4), 'f8': ('d', 8),
            'i1': ('b', 1), 'i2': ('h', 2), 'i4': ('i', 4), 'i8': ('q', 8),
            'u1': ('B', 1), 'u2': ('H', 2), 'u4': ('I', 4), 'u8': ('Q', 8),
        }
        try:
            raw = base64.b64decode(v["bdata"])
            fmt_char, size = DTYPE_MAP.get(v["dtype"], ('d', 8))
            count = len(raw) // size
            return list(struct.unpack(f'<{count}{fmt_char}', raw))
        except Exception:
            return []
    # Handle numpy scalars and arrays
    try:
        import numpy as np
        if isinstance(v, np.integer): return int(v)
        if isinstance(v, np.floating): return float(v)
        if isinstance(v, np.ndarray): return [force_primitive(x) for x in v.tolist()]
    except ImportError:
        pass
    if isinstance(v, dict): return {str(k): force_primitive(val) for k, val in v.items()}
    if isinstance(v, (list, tuple, set)): return [force_primitive(x) for x in v]
    return str(v)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})

# ================= MODELS =================
class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None
    custom_db_id: str | None = None  # Set when user has uploaded a custom DB

# ================= ROUTES =================
@app.get("/")
async def root():
    return FileResponse(os.path.join(BASE_DIR, "frontend", "index.html"))

@app.get("/health")
async def health():
    """Standard health check endpoint for load balancers and monitoring."""
    try:
        # Create a fresh LLM client to check the actual provider (avoids cached core)
        from src.llm.client import LLMClient
        fresh_client = LLMClient()
        provider_info = fresh_client.get_provider_info()
    except Exception:
        provider_info = {"provider": "unknown", "available": False}
    return {
        "status": "ok",
        "llm_provider": provider_info.get("provider"),
        "model": provider_info.get("model"),
        "llm_available": provider_info.get("available")
    }

@app.get("/api/atlas")
async def get_atlas():
    """Returns the visual topology of the database schema with safety validation."""
    try:
        core = get_core()
        schema = core.get("schema_info", {})
        if not schema or not schema.get("tables"):
            # Attempt to re-pull schema if empty
            schema = core["schema_analyzer"].get_schema_info()
            core["schema_info"] = schema

        if not schema or not schema.get("tables"):
            return JSONResponse(content={"nodes": [], "edges": []})

        nodes = [{"id": t, "label": t.upper()} for t in schema.get("tables", {}).keys()]
        edges = [{"from": r["from_table"], "to": r["to_table"]} for r in schema.get("relationships", [])]
        return JSONResponse(content={"nodes": nodes, "edges": edges})
    except Exception as e:
        print(f"Atlas Topology Fault: {e}", flush=True)
        return JSONResponse(content={"nodes": [], "edges": []})

@app.get("/api/dashboard")
async def get_dashboard():
    """Generates the Agentic 'Business Pulse' view with Zero-Failure serialization."""
    try:
        core = get_core()
        llm_dashboard = core["parser_llm"].generate_dynamic_dashboard(core["schema_info"])

        if not llm_dashboard:
            return JSONResponse(status_code=503, content={"success": False, "error": "Nexus Brain is currently offline."})

        kpis = []
        for k in llm_dashboard.get("kpis", []):
            try:
                res = core["execution_engine"].execute(k.get("sql", ""))
                val = 0.0
                if res.success and res.data:
                    row = res.data[0]
                    val = float(next(iter(row.values())) or 0.0)
                kpis.append({"label": k.get("label"), "value": val, "format": k.get("format")})
            except: continue

        dashboard_charts = []
        for c in llm_dashboard.get("charts", []):
            try:
                res = core["execution_engine"].execute(c.get("sql", ""))
                if res.success and res.data:
                    fig = core["viz_generator"].generate_chart(res.data, {"metric": c.get("label")}, chart_type=c.get("type", "bar"))
                    if fig:
                        # Convert to plain dict first, then force all values to primitives
                        chart_dict = force_primitive(fig.to_dict())
                        dashboard_charts.append(chart_dict)
            except Exception as ce:
                print(f"Chart Fault: {ce}")
                continue

        response_data = force_primitive({
            "success": True,
            "kpis": kpis,
            "dashboard_charts": dashboard_charts
        })
        return JSONResponse(content=jsonable_encoder(response_data))
    except Exception as e:
        print(f"Dashboard Hub Fault: {e}", flush=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.post("/api/upload-db")
async def upload_database(file: UploadFile = File(...)):
    """Accept a SQLite database file upload. Returns a session_id for subsequent queries."""
    # Validate file type
    allowed_extensions = {".db", ".sqlite", ".sqlite3"}
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file_ext}'. Allowed: .db, .sqlite, .sqlite3"
        )

    # Size limit: 100MB
    MAX_SIZE = 100 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB.")

    # Verify SQLite magic bytes
    if not content.startswith(b"SQLite format 3"):
        raise HTTPException(status_code=400, detail="File is not a valid SQLite database.")

    # Save with unique session ID
    session_id = str(uuid.uuid4())
    db_path = os.path.join(UPLOAD_DIR, f"{session_id}.db")
    with open(db_path, "wb") as f:
        f.write(content)

    # Build schema immediately
    try:
        core = get_custom_core(session_id, db_path)
        schema_info = core["schema_info"]
        table_names = list(schema_info["tables"].keys())
        rel_count = len(schema_info["relationships"])
    except Exception as e:
        os.remove(db_path)
        raise HTTPException(status_code=422, detail=f"Could not read database schema: {e}")

    return {
        "success": True,
        "session_id": session_id,
        "filename": file.filename,
        "tables": table_names,
        "table_count": len(table_names),
        "relationship_count": rel_count,
        "schema": {
            t: list(info["columns"].keys())
            for t, info in schema_info["tables"].items()
        }
    }

@app.delete("/api/upload-db/{session_id}")
async def remove_uploaded_database(session_id: str):
    """Clean up an uploaded database and its in-memory core."""
    db_path = os.path.join(UPLOAD_DIR, f"{session_id}.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    _custom_cores.pop(session_id, None)
    return {"success": True}

@app.post("/api/query")
async def handle_query(request: QueryRequest, api_key: str = Depends(verify_api_key)):
    """Executes natural language queries — supports both built-in and user-uploaded databases."""
    start_time = time.time()
    try:


        from src.core.confidence import ConfidenceScorer
        from src.core.intent_parser import QueryFilters, QueryIntent

        # Route to the correct core (custom uploaded DB or default)
        if request.custom_db_id:
            db_path = os.path.join(UPLOAD_DIR, f"{request.custom_db_id}.db")
            if not os.path.exists(db_path):
                return JSONResponse(status_code=404, content={
                    "success": False,
                    "error": "Uploaded database session not found. Please re-upload your file."
                })
            core = get_custom_core(request.custom_db_id, db_path)
        else:
            core = get_core()

        intent_dict = core["parser_llm"].parse(request.query, core["schema_info"])

        if not intent_dict:
            metrics_recorder.record_query_latency("/api/query", time.time() - start_time, False)
            metrics_recorder.record_error("/api/query", "llm_unavailable")
            return JSONResponse(content={
                "success": False,
                "error": "Nexus Brain is offline. Please use simpler queries like 'Total Revenue'.",
                "data": {"results": []}
            })

        # Coerce dict -> QueryIntent
        try:
            raw_filters = intent_dict.get("filters") or {}
            if isinstance(raw_filters, dict):
                filters_obj = QueryFilters(**{k: v for k, v in raw_filters.items() if k in QueryFilters.model_fields})
            else:
                filters_obj = QueryFilters()
            intent = QueryIntent(
                metric=intent_dict.get("metric", ""),
                aggregation=intent_dict.get("aggregation", "sum"),
                group_by=intent_dict.get("group_by"),
                filters=filters_obj,
                limit=intent_dict.get("limit", 10) or 10,
                chart=intent_dict.get("chart", "auto") or "auto",
                sql_query=intent_dict.get("sql_query", "") or "",
            )
        except Exception:
            intent = QueryIntent(metric=intent_dict.get("metric", ""), sql_query=intent_dict.get("sql_query", ""))

        sql = intent.sql_query
        params = {}
        if not sql:
            sql, params = core["query_generator"].generate(intent, core["schema_info"])

        res = core["execution_engine"].execute(sql, params)
        chart = None
        if res.data:
            fig = core["viz_generator"].generate_chart(res.data, intent_dict)
            if fig:
                chart = force_primitive(fig.to_dict())

        expl = core["explanation_generator"].generate(intent_dict, sql, res.data)

        # Confidence scoring
        confidence_scorer = ConfidenceScorer()
        schema_context = core["parser_llm"]._build_schema_context(core["schema_info"])
        confidence = confidence_scorer.score(
            original_query=request.query,
            sql=sql,
            schema_context=schema_context,
            schema_info=core["schema_info"],
            execution_engine=core["execution_engine"],
        )

        # Pull instrumentation from the LLM client
        usage = getattr(core["parser_llm"].llm, "last_usage", {})

        # Record metrics
        latency = time.time() - start_time
        success = res.success
        metrics_recorder.record_query_latency("/api/query", latency, success)

        if usage:
            provider = usage.get("provider", "unknown")
            model = usage.get("model", "unknown")
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            cost_usd = usage.get("cost_usd", 0.0)

            metrics_recorder.record_tokens(provider, model, prompt_tokens, completion_tokens)
            metrics_recorder.record_cost(provider, model, cost_usd)

        if not success:
            metrics_recorder.record_error("/api/query", "execution_failed")

        metrics_recorder.record_confidence(confidence.overall_confidence)
        metrics_recorder.record_hallucination(confidence.hallucination_flag)
        if confidence.multi_query_flag is not None:
            metrics_recorder.record_multi_query_disagreement(confidence.multi_query_flag)

        return JSONResponse(content=jsonable_encoder(force_primitive({
            "success": True,
            "explanation": expl,
            "visualization": chart,
            "data": {"results": res.data},
            "metadata": {
                "generated_sql": sql,
                "usage": usage,
                "db_source": "custom" if request.custom_db_id else "built-in",
                "confidence": {
                    "overall": confidence.overall_confidence,
                    "back_translation_score": confidence.back_translation_score,
                    "back_translated_question": confidence.back_translated_question,
                    "hallucination_flag": confidence.hallucination_flag,
                    "multi_query_agreement": confidence.multi_query_agreement,
                    "multi_query_flag": confidence.multi_query_flag,
                }
            }
        })))
    except Exception as e:
        metrics_recorder.record_query_latency("/api/query", time.time() - start_time, False)
        metrics_recorder.record_error("/api/query", type(e).__name__)
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/api/table/{name}")
async def get_table_details(name: str):
    """Deep node exploration: returns schema and sample records for a table."""
    try:
        core = get_core()
        schema = core["schema_info"]
        table_info = schema.get("tables", {}).get(name)

        if not table_info:
            raise HTTPException(status_code=404, detail="Table not found")

        # Get sample data using the execution engine (Lite-Core style)
        sql = f"SELECT * FROM {name} LIMIT 5"
        res = core["execution_engine"].execute(sql)

        return force_primitive({
            "name": name,
            "description": table_info.get("description", ""),
            "columns": table_info.get("columns", {}),
            "sample_data": res.data if res.success else []
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sample-queries")
async def get_samples():
    return [
        {"query": "Show average salary by department", "category": "HR"},
        {"query": "Total budget across all regions", "category": "HR"},
        {"query": "Employee count by department", "category": "HR"},
        {"query": "List campaign ROI percentages", "category": "CRM"},
        {"query": "Average sentiment score by customer", "category": "CRM"},
        {"query": "Compare total LTV by industry", "category": "CRM"},
        {"query": "Inventory levels across warehouses", "category": "Supply Chain"},
        {"query": "Show suppliers by rating", "category": "Supply Chain"},
        {"query": "Recent shipments by status", "category": "Supply Chain"},
        {"query": "Total revenue generated by sales rep", "category": "Finance"},
        {"query": "Sum of unpaid invoices amounts", "category": "Finance"},
        {"query": "Count of orders by status", "category": "Sales"},
        {"query": "Show top 10 most expensive products", "category": "Sales"},
        {"query": "Total order amount over time", "category": "Finance"},
        {"query": "Total warehouse capacity by location", "category": "Supply Chain"}
    ]

@app.get("/api/debug/query")
async def debug_query(q: str = "show revenue trends"):
    """Debug endpoint: shows what intent and SQL is generated for a query."""
    try:
        core = get_core()
        intent_dict = core["parser_llm"].parse(q, core["schema_info"])
        if not intent_dict:
            return {"intent": None, "sql": None}
        sql = intent_dict.get("sql_query") or "(no sql in intent)"
        res = core["execution_engine"].execute(sql) if intent_dict.get("sql_query") else None
        return {
            "intent": intent_dict,
            "sql": sql,
            "rows": len(res.data) if res and res.data else 0,
            "error": res.error if res else None,
            "db_path": core["execution_engine"].db_path
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

# Prometheus metrics endpoint
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Expose Prometheus metrics in text format."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Nexus API Server: Network listener activated on port {port}.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
