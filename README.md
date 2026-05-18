# QueryMind AI - Enterprise Analytics Platform

QueryMind AI is a state-of-the-art, local-first analytics dashboard and SQL-generation platform. Designed for enterprise data exploration, it allows users to ask complex natural language questions against a massive, highly interconnected relational database, instantaneously compiling intelligent visualizations and explanations without writing a single line of code.

## 🚀 Key Frameworks & Technologies

QueryMind AI is built on a highly modular, decoupled stack designed for both extreme speed and aesthetic premium design:

### Backend
- **Framework**: `FastAPI` (Python)
- **Server**: `Uvicorn` (Asynchronous ASGI server)
- **Database**: Native `SQLite3` (Populated automatically with a 14-table, heavily seeded synthetic Corporate Enterprise DB).
- **Core Logic**: Pure Python standard library with multi-agent orchestration.

### AI / Generative Engine
- **LLM Provider**: Built natively around local **Ollama** models (default: `qwen2.5:3b`) to guarantee 100% data privacy when scanning corporate schemas.
- **Fallbacks**: Fault-tolerant network proxying using `httpx`. The engine gracefully falls back to intelligent, regex-based offline parsing if the Ollama endpoint ever crashes.
- *(Note: It includes native adapters for OpenAI `gpt-4o-mini` if API keys are provided via the environment).*

### Frontend
- **Structure**: Vanilla DOM manipulation (`app.js`) paired with standard HTML5. No heavy frameworks like React or Vue were used, keeping the static bundle incredibly lightweight.
- **Styling**: Vanilla modern CSS3 focusing on premium styling paradigms (Glassmorphism, animated gradients, high-contrast Dark Mode).
- **Visualization Engines**:
  - `Plotly`: Handled by the backend agent for mathematical charting.
  - `Vis-Network`: Powers the **Atlas Topology Explorer**, visualizing the database's foreign key relationships in a physics-based, 3D force-directed nodal graph.

---

## 🧠 The Multi-Agent Pipeline Architecture

Instead of relying on a monolithic LLM call that is prone to hallucination, the QueryMind intelligence engine uses a highly specialized **Multi-Agent Pipeline**. When you ask a question like *"Show average salary by department"*, the query is processed chronologically by these autonomous agents:

1. **`IntentParserLLM` (The Planner)**
   - Merges the user's messy natural language with the massive 14-table database schema context. Extrapolates a strict JSON `QueryIntent` (e.g., Identifying the metric, aggregation type, and group-by clauses).
2. **`QueryValidator` & `SchemaAnalyzer` (The Security Guards)**
   - Sandboxes the execution. Scans the parsed intent to ensure no data mutation (e.g., `DROP`, `UPDATE`) occurs, and cross-references table/column requests against the active SQLite schema.
3. **`QueryGenerator` (The Engineer)**
   - Transpiles the safe `QueryIntent` JSON into a syntactically perfect SQL string. It intelligently manages SQL `JOIN` logic connecting disparate domain tables (e.g., linking `salaries` across `employees` to `departments`).
4. **`ExecutionEngine` (The Runner)**
   - Securely locks the database and runs the raw SQL calculation, extracting the raw mathematical row payload.
5. **`VizGenerator` (The Designer)**
   - Analyzes the shape of the numerical return tensor. If it detects time-series bounds, it forces a Line Chart; if categorical groupings, it creates a Pie or Bar chart payload.
6. **`ExplanationGenerator` (The Analyst)**
   - Contextualizes the entire execution flow. Takes the raw numbers and outputs a smart, human-readable summary that streams into the UI via the frontend's typewriter effect.

---

## 🏗️ The Enterprise Schema

The backend dynamically bootstraps a complex corporate structure comprising four massive domains:

- **Human Resources**: `employees`, `departments`, `salaries`
- **Supply Chain**: `inventory`, `warehouses`, `shipments`, `suppliers`
- **Sales & Finance**: `invoices`, `orders`, `order_items`, `products`
- **CRM / Customer Relations**: `customers`, `campaigns`, `interactions`

This massive dataset allows the System Agents to trace incredibly complex LTV (Lifetime Value) metrics alongside operational costs organically.

---

## 💻 Getting Started

To launch the Command Center:

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the Uvicorn/FastAPI Gateway on port `8000`:
   ```bash
   python api.py
   ```
3. Open your browser to `http://localhost:8000/`. The system will lazily construct the massive Corporate Database automatically on your first interaction!

---

## 🛠️ Project History & Refinements

This project evolved significantly from a lightweight proof-of-concept into a resilient, production-ready enterprise tool:

- **Premium UI/UX Overhaul**: Upgraded the standard interface to use deep Dark Mode styling, Glassmorphism panels, CSS3 animations, and dynamic pulse typewriters to mimic a high-end corporate dashboard.
- **Atlas Physics Stabilization**: Fine-tuned the `forceAtlas2Based` physics engine powering the Atlas Topology Explorer. We drastically increased `damping` to prevent the nodes from constantly spinning out of control, resulting in a beautiful, stable 3D relationship map.
- **Resilient AI Handling**: Engineered robust fault-tolerance. If the local Ollama LLM throws an Out-Of-Memory (OOM) `500 Server Error`, the backend automatically queues and retries the request seamlessly.
- **Offline Fallback Engine**: If the AI ultimately fails, the backend doesn't crash. It dynamically maps keywords routing to the 14 corporate tables implicitly, guaranteeing the dashboard never breaks.

---

## 🐘 Scaling to PostgreSQL & Other Databases

While QueryMind AI ships natively with a local SQLite database for frictionless setup and testing, the core architectural logic is entirely **Database Agnostic**.

If you wish to scale this up to a live cloud database like **PostgreSQL**, **MySQL**, or **Snowflake**, the framework requires virtually no changes to the AI pipeline:

1. **Swap the Driver**: Update the connection string in the `ExecutionEngine` to use a heavy-duty connector (e.g., `psycopg2` or `SQLAlchemy` for Postgres).
2. **Dynamic Schema Extraction**: Instead of generating the synthetic tables natively, replace `get_schema()` with a function that executes `SELECT * FROM information_schema.tables` to automatically pull in your live cloud schema.
3. **The LLM Adapts Natively**: Because the `IntentParserLLM` simply reads whatever JSON mapping the schema function returns, the AI will organically map your new PostgreSQL tables into its context window instantly. The `QueryGenerator` will then automatically output standard SQL compliant with your newly connected database.
