"""LLM Client wrapper for QueryMind AI - Supports Ollama and OpenAI."""
import json
import os
import re
from typing import Any

import httpx


class LLMClient:
    """
    Unified LLM client supporting NVIDIA Nemotron, Gemini, Ollama (local) and OpenAI (cloud).
    
    Auto-detects available provider based on configuration.
    """

    DEFAULT_OLLAMA_MODEL = "qwen2.5:1.5b"  # ~1 GiB RAM — safe for 12 GiB systems
    DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
    DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
    NVIDIA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        provider: str = "auto",  # "auto", "ollama", or "openai"
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key

        # Determine provider
        self._actual_provider = self._detect_provider()

        # Configure based on provider
        self._setup_provider()

        self._client: httpx.Client | None = None

        # Instrumentation stats
        self.last_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
            "provider": self._actual_provider,
            "model": self.model
        }

    def _detect_provider(self) -> str:
        """Detect which LLM provider to use."""
        if self.provider != "auto":
            return self.provider

        # Check for OpenAI key first
        openai_key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            return "openai"

        # Check for NVIDIA key
        nvidia_key = os.environ.get("NVIDIA_API_KEY", "")
        if nvidia_key:
            return "nvidia"

        # Check if Ollama is available
        if self._check_ollama():
            return "ollama"

        # Check if Gemini key is available
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if gemini_key:
            return "gemini"

        # Default to Ollama if available, otherwise none
        return "ollama" if self._check_ollama() else "none"

    def _check_ollama(self) -> bool:
        """Check if Ollama is available with a strict low timeout."""
        import httpx
        try:
            # Sub-second timeout prevents boot hang on resource-starved systems
            response = httpx.get("http://localhost:11434/api/tags", timeout=0.5)
            return response.status_code == 200
        except Exception:
            return False

    def _setup_ollama(self):
        """Setup Ollama configuration."""
        self.base_url = "http://localhost:11434"
        # OLLAMA_MODEL env var overrides the default — useful to pin a small model per machine
        self.model = self.model or os.environ.get("OLLAMA_MODEL", self.DEFAULT_OLLAMA_MODEL)
        self.temperature = 0.2
        self._requires_structured_output = False

    def _setup_openai(self):
        """Setup OpenAI configuration."""
        self.api_key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = "https://api.openai.com/v1"
        self.model = self.model or self.DEFAULT_OPENAI_MODEL
        self.temperature = 0.2
        self._requires_structured_output = True

    def _setup_nvidia(self):
        """Setup NVIDIA Nemotron configuration."""
        self.api_key = os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self.model = self.model or self.NVIDIA_MODEL
        self.temperature = 0.2
        self._requires_structured_output = True

    def _setup_gemini(self):
        """Setup Gemini configuration."""
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = self.model or self.DEFAULT_GEMINI_MODEL
        self.temperature = 0.2
        self._requires_structured_output = True

    @property
    def client(self) -> httpx.Client:
        """Lazy initialization of HTTP client."""
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self._actual_provider in ("openai", "nvidia", "gemini") and self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.Client(
                headers=headers,
                timeout=120.0,  # Longer timeout for local models
            )
        return self._client

    def _setup_provider(self):
        """Setup the appropriate provider configuration."""
        if self._actual_provider == "ollama":
            self._setup_ollama()
        elif self._actual_provider == "openai":
            self._setup_openai()
        elif self._actual_provider == "nvidia":
            self._setup_nvidia()
        elif self._actual_provider == "gemini":
            self._setup_gemini()
        else:
            # Default to Ollama
            self._setup_ollama()

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    @property
    def is_available(self) -> bool:
        """Check if LLM is available."""
        if self._actual_provider == "ollama":
            return self._check_ollama()
        return bool(self.api_key)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str | None:
        """Send a chat completion request with auto-fallback and retry on 500 errors."""
        import time
        if not self.is_available:
            return None

        start_time = time.time()
        for attempt in range(5):
            try:
                self._setup_provider()  # Ensure provider is configured
                if self._actual_provider == "ollama":
                    result = self._ollama_chat(messages, temperature, max_tokens)
                elif self._actual_provider == "nvidia":
                    result = self._nvidia_chat(messages, temperature, max_tokens)
                elif self._actual_provider == "gemini":
                    result = self._gemini_chat(messages, temperature, max_tokens)
                else:
                    result = self._openai_chat(messages, temperature, max_tokens)

                # Update latency
                self.last_usage["latency_ms"] = int((time.time() - start_time) * 1000)
                self.last_usage["provider"] = self._actual_provider
                self.last_usage["model"] = self.model
                return result
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 503) and attempt < 4:
                    wait = min(2 ** attempt * 5, 60)  # 5s, 10s, 20s, 40s, max 60s
                    print(f"{self._actual_provider.upper()} {e.response.status_code} (attempt {attempt+1}/5), waiting {wait}s...")
                    time.sleep(wait)
                    continue
                print(f"{self._actual_provider.upper()} failed, falling back: {e}")
                break
            except Exception as e:
                print(f"{self._actual_provider.upper()} failed, falling back: {e}")
                break

        return None

    def _openai_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str | None:
        """Ollama chat completion."""
        # Convert messages to Ollama format
        ollama_messages = []
        system_msg = None

        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                ollama_messages.append(msg)

        # Put system prompt in first user message if exists
        if system_msg:
            if ollama_messages and ollama_messages[0]["role"] == "user":
                ollama_messages[0]["content"] = f"{system_msg}\n\n{ollama_messages[0]['content']}"

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        response = self.client.post(
            f"{self.base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        # Instrument Ollama usage (estimated if not provided)
        # Note: Ollama usually provides 'prompt_eval_count' and 'eval_count'
        p_tokens = data.get("prompt_eval_count", len(str(messages)) // 4)
        c_tokens = data.get("eval_count", len(data["message"]["content"]) // 4)
        self.last_usage.update({
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": p_tokens + c_tokens,
            "cost_usd": 0.0  # Local models are free!
        })

        return data["message"]["content"]

    def _openai_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str | None:
        """OpenAI chat completion."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        response = self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        # Instrument OpenAI usage and cost
        usage = data.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)

        # Heuristic cost for gpt-4o-mini ($0.15 / 1M input, $0.60 / 1M output)
        cost = (p_tokens * 0.15 / 1_000_000) + (c_tokens * 0.60 / 1_000_000)

        self.last_usage.update({
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": p_tokens + c_tokens,
            "cost_usd": round(cost, 6)
        })

        return data["choices"][0]["message"]["content"]

    def _nvidia_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str | None:
        """NVIDIA Nemotron 3 Ultra chat completion."""
        # NVIDIA uses OpenAI-compatible API
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        response = self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]

        # Instrument NVIDIA usage and cost
        usage = data.get("usage", {})
        p_tokens = usage.get("prompt_tokens", len(str(messages)) // 4)
        c_tokens = usage.get("completion_tokens", len(content) // 4)

        # Heuristic cost for Nemotron (similar to GPT-4o-mini scale)
        cost = (p_tokens * 0.15 / 1_000_000) + (c_tokens * 0.60 / 1_000_000)

        self.last_usage.update({
            "provider": "nvidia",
            "model": self.model,
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": p_tokens + c_tokens,
            "cost_usd": round(cost, 6),
        })

        return content

    def structured_output(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
    ) -> dict[str, Any] | None:
        """Get structured JSON output from LLM."""
        if not self.is_available:
            return None

        # Add schema instruction to prompt
        schema_instruction = f"\n\nIMPORTANT: Output ONLY valid JSON matching this schema:\n{json.dumps(response_schema, indent=2)}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt + schema_instruction},
        ]

        try:
            self._setup_provider()  # Ensure provider is configured
            if self._actual_provider == "ollama":
                return self._ollama_structured_output(messages, response_schema, temperature)
            elif self._actual_provider == "nvidia":
                return self._nvidia_structured_output(messages, response_schema, temperature)
            elif self._actual_provider == "gemini":
                return self._gemini_structured_output(messages, response_schema, temperature)
            else:
                return self._openai_structured_output(messages, response_schema, temperature)
        except Exception as e:
            print(f"Structured output error: {e}")
            return None

    def _nvidia_structured_output(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any] | None:
        """NVIDIA structured output using JSON mode."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "query_intent",
                    "schema": response_schema,
                },
            },
        }

        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Record usage
            usage = data.get("usage", {})
            p_tokens = usage.get("prompt_tokens", len(str(messages)) // 4)
            c_tokens = usage.get("completion_tokens", len(content) // 4)

            # Heuristic pricing for NVIDIA Nemotron 3 Ultra (similar to GPT-4o-mini scale)
            cost = (p_tokens * 0.15 / 1_000_000) + (c_tokens * 0.60 / 1_000_000)

            self.last_usage.update({
                "provider": "nvidia",
                "model": self.model,
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens,
                "cost_usd": round(cost, 6),
            })

            return json.loads(content)
        except json.JSONDecodeError:
            return self._extract_json(content)
        except Exception as e:
            print(f"NVIDIA structured output error: {e}")
            return None

    def _gemini_structured_output(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any] | None:
        """Gemini structured output."""
        # Convert messages to Gemini format
        gemini_messages = []
        system_prompt = None

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                gemini_messages.append({"role": msg["role"], "parts": [{"text": msg["content"]}]})

        # Prepend system prompt to first user message
        if system_prompt and gemini_messages and gemini_messages[0]["role"] == "user":
            gemini_messages[0]["parts"][0]["text"] = f"{system_prompt}\n\n{gemini_messages[0]['parts'][0]['text']}"

        payload = {
            "contents": gemini_messages,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2000,
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }

        try:
            response = self.client.post(
                f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]

            # Record usage
            usage = data.get("usageMetadata", {})
            p_tokens = usage.get("promptTokenCount", len(str(messages)) // 4)
            c_tokens = usage.get("candidatesTokenCount", len(content) // 4)

            cost = (p_tokens * 0.075 / 1_000_000) + (c_tokens * 0.30 / 1_000_000)

            self.last_usage.update({
                "provider": "gemini",
                "model": self.model,
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens,
                "cost_usd": round(cost, 6),
            })

            return json.loads(content)
        except json.JSONDecodeError:
            return self._extract_json(content)
        except Exception as e:
            print(f"Gemini structured output error: {e}")
            return None

    def _ollama_structured_output(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any] | None:
        """Ollama structured output - parse from text."""
        content = self.chat(messages, temperature=temperature, max_tokens=1500)

        if not content:
            return None

        # Extract JSON from response
        return self._extract_json(content)

    def _openai_structured_output(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        temperature: float,
    ) -> dict[str, Any] | None:
        """OpenAI structured output using JSON mode."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "query_intent",
                    "schema": response_schema,
                },
            },
        }

        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Record usage
            usage = data.get("usage", {})
            p_tokens = usage.get("prompt_tokens", len(str(messages)) // 4)
            c_tokens = usage.get("completion_tokens", len(content) // 4)

            cost = (p_tokens * 0.15 / 1_000_000) + (c_tokens * 0.60 / 1_000_000)

            self.last_usage.update({
                "provider": "openai",
                "model": self.model,
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens,
                "cost_usd": round(cost, 6),
            })

            return json.loads(content)
        except json.JSONDecodeError:
            return self._extract_json(content)
        except Exception as e:
            print(f"OpenAI structured output error: {e}")
            return None

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Extract JSON from text response."""
        # Try to find JSON in the text
        text = text.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def generate_insights(
        self,
        query: str,
        sql: str,
        data: dict[str, Any],
        context: str,
    ) -> str | None:
        """Generate human-like insights from query results."""
        if not self.is_available:
            return None

        data_summary = self._summarize_data(data)

        system_prompt = """You are a data analyst AI. Generate human-like insights from query results.
Be concise, insightful, and actionable. Focus on:
- Key findings and trends
- Notable patterns or anomalies
- Business implications

Output ONLY a natural language paragraph, no JSON."""

        user_prompt = f"""Query: {query}
SQL: {sql}
Data Summary:
{data_summary}

Context: {context}

Generate insights:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return self.chat(messages, temperature=0.5, max_tokens=500)

    def _summarize_data(self, data: dict[str, Any]) -> str:
        """Summarize data for LLM context."""
        if isinstance(data, dict):
            rows = data.get("data", [])
            if rows:
                sample = rows[:5]
                return f"Results ({data.get('row_count', len(rows))} rows): {json.dumps(sample, default=str)}"
        return str(data)[:500]

    def get_provider_info(self) -> dict[str, Any]:
        """Get information about current provider."""
        return {
            "provider": self._actual_provider,
            "model": self.model,
            "available": self.is_available,
        }


class IntentParserLLM:
    """LLM-powered intent parser for complex queries."""

    SCHEMA = {
        "type": "object",
        "properties": {
            "metric": {"type": "string", "description": "The metric to query (e.g., revenue, sales, count)"},
            "aggregation": {"type": "string", "enum": ["sum", "count", "avg", "min", "max"]},
            "group_by": {"type": "string", "nullable": True},
            "filters": {
                "type": "object",
                "properties": {
                    "time_range": {"type": "string", "nullable": True},
                    "city": {"type": "string", "nullable": True},
                    "category": {"type": "string", "nullable": True},
                },
            },
            "limit": {"type": "integer"},
            "chart": {"type": "string", "enum": ["bar", "line", "pie", "area"], "description": "The absolute most optimal visualization chart type for formatting the provided sql dimensions."},
            "sql_query": {"type": "string", "description": "The exact valid raw SQLite query. Join tables strictly based on the relationships in the schema context. Do not use alias names for columns that do not exist."},
        },
        "required": ["metric", "aggregation", "sql_query"],
    }

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client

    def parse(self, query: str, schema_info: dict, previous_intent: dict | None = None) -> dict | None:
        """Parse complex query using LLM with Standalone fallback."""
        if not self.llm or not self.llm.is_available:
            return self.parse_standalone(query, schema_info)

        # Build table list for hard constraint in prompt
        table_names = list(schema_info.get("tables", {}).keys())
        table_list_str = ", ".join(table_names) if table_names else "(no tables found)"
        schema_context = self._build_schema_context(schema_info)

        refinement_context = ""
        if previous_intent:
            refinement_context = f"\nPrevious query context: {json.dumps(previous_intent)}"

        system_prompt = f"""You are a SQL query builder. Convert natural language queries into structured JSON.

CRITICAL RULES:
1. You MUST ONLY use the tables and columns listed in the schema below.
2. NEVER invent, guess, or use tables not in this list: {table_list_str}
3. Write the sql_query field as a valid SQLite SELECT statement using ONLY these exact table names.
4. If the user asks about tables or schema, write a query that uses sqlite_master or the tables listed.
5. Column names must exactly match the schema — they are case-sensitive.

Available schema:
{schema_context}

Output JSON matching this schema:
{json.dumps(self.SCHEMA, indent=2)}

If this is a refinement of a previous query, merge with previous intent.{refinement_context}"""

        user_prompt = f"Parse this query and generate SQL using ONLY the tables listed above: {query}"

        result = self.llm.structured_output(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=self.SCHEMA,
        )

        # Validate: LLM sometimes echoes the schema template instead of filling it in.
        # A valid result must have 'sql_query' as a direct string key, not nested in 'properties'.
        if not result:
            return self.parse_standalone(query, schema_info)
        if not isinstance(result, dict):
            return self.parse_standalone(query, schema_info)
        if "properties" in result or "type" in result:
            # LLM returned the schema definition, not the instance — fall back
            print("LLM returned schema echo — falling back to standalone parser.", flush=True)
            return self.parse_standalone(query, schema_info)
        if not result.get("sql_query"):
            # No SQL generated — fall back
            return self.parse_standalone(query, schema_info)
        return result

    def parse_standalone(self, query: str, schema_info: dict) -> dict | None:
        """
        Schema-driven offline fallback — generates SQL dynamically from live schema_info.
        Never uses hardcoded table names. Works with any uploaded database.
        """
        q = query.lower()
        tables = schema_info.get("tables", {})
        table_names = list(tables.keys())

        if not table_names:
            return {"metric": "records", "aggregation": "count", "group_by": None,
                    "chart": "bar", "sql_query": "SELECT 'No tables found' AS error"}

        # Meta-queries about the database structure itself
        if any(w in q for w in ["how many table", "list table", "show table", "what table", "all table"]):
            names_list = ", ".join(f"'{t}'" for t in table_names)
            return {
                "metric": "tables", "aggregation": "count", "group_by": None, "chart": "bar",
                "sql_query": f"SELECT name FROM sqlite_master WHERE type='table' AND name IN ({names_list}) ORDER BY name"
            }

        # Try to find the best matching table from the query keywords
        def pick_table(keywords):
            for kw in keywords:
                for t in table_names:
                    if kw in t.lower():
                        return t
            return None

        # Detect intent and pick matching table
        matched_table = None
        intent_sql = None

        # SELECT / show rows
        if any(w in q for w in ["show", "list", "display", "get", "fetch", "first", "row"]):
            # Try to find mentioned table name directly in query
            for t in table_names:
                if t.lower() in q:
                    matched_table = t
                    break
            if not matched_table:
                matched_table = table_names[0]
            limit = 10
            for word in q.split():
                if word.isdigit():
                    limit = int(word)
                    break
            intent_sql = f'SELECT * FROM "{matched_table}" LIMIT {limit}'
            return {"metric": "records", "aggregation": "count", "group_by": None, "chart": "bar", "sql_query": intent_sql}

        # COUNT queries
        if any(w in q for w in ["count", "how many", "total number", "number of"]):
            for t in table_names:
                if t.lower() in q:
                    matched_table = t
                    break
            if not matched_table:
                matched_table = table_names[0]
            intent_sql = f'SELECT COUNT(*) as count FROM "{matched_table}"'
            return {"metric": "count", "aggregation": "count", "group_by": None, "chart": "bar", "sql_query": intent_sql}

        # Aggregation queries (sum/avg/revenue/total)
        if any(w in q for w in ["revenue", "sale", "total", "sum", "average", "avg"]):
            matched_table = pick_table(["invoice", "order", "sale", "transaction", "payment"]) or table_names[0]
            tinfo = tables.get(matched_table, {})
            cols = list(tinfo.get("columns", {}).keys())
            # Find a numeric column to sum
            numeric_col = next((c for c in cols if any(k in c.lower() for k in ["total", "amount", "price", "revenue", "cost", "salary", "value"])), cols[0] if cols else "*")
            intent_sql = f'SELECT SUM("{numeric_col}") as total FROM "{matched_table}"'
            return {"metric": numeric_col, "aggregation": "sum", "group_by": None, "chart": "bar", "sql_query": intent_sql}

        # Default: show first 10 rows from most likely table
        for t in table_names:
            if t.lower() in q:
                matched_table = t
                break
        if not matched_table:
            matched_table = table_names[0]
        return {
            "metric": "records", "aggregation": "count", "group_by": None, "chart": "bar",
            "sql_query": f'SELECT * FROM "{matched_table}" LIMIT 10'
        }

    def generate_dynamic_dashboard(self, schema_info: dict) -> dict | None:
        """Dynamically generate dashboard with Standalone fallback."""
        if not self.llm or not self.llm.is_available:
            return self.generate_dashboard_standalone(schema_info)

        schema_context = self._build_schema_context(schema_info)

        system_prompt = """You are an expert AI Data Analyst. Your job is to automatically build a dashboard based on a given database schema.
Analyze the provided schema and create 3 key performance indicators (KPIs) and 2 powerful time-series visualization queries.
Return the result strictly as JSON."""

        user_prompt = f"Schema Context:\n{schema_context}\n\nGenerate the JSON output representing 3 distinct KPIs and 2 Charts."

        json_schema = {
            "type": "object",
            "properties": {
                "kpis": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Human readable KPI label (e.g., Total Revenue)"},
                            "sql": {"type": "string", "description": "Single-scalar SQLite query"},
                            "format": {"type": "string", "enum": ["number", "currency"]}
                        },
                        "required": ["label", "sql", "format"]
                    }
                },
                "charts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Visualization title"},
                            "sql": {"type": "string", "description": "SQLite query returning exactly 2 columns to plot."},
                            "type": {"type": "string", "enum": ["bar", "line", "pie", "area"], "description": "Best chart type for this data"}
                        },
                        "required": ["label", "sql", "type"]
                    }
                }
            },
            "required": ["kpis", "charts"]
        }

        result = self.llm.structured_output(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=json_schema,
            temperature=0.3
        )

        if not result:
            return self.generate_dashboard_standalone(schema_info)
        return result

    def generate_dashboard_standalone(self, schema_info: dict) -> dict:
        """
        Schema-driven dashboard fallback — no hardcoded SQL.
        Inspects the live schema to find numeric, date, and categorical columns
        and builds KPI + chart queries dynamically.
        """
        tables = schema_info.get("tables", {})
        relationships = schema_info.get("relationships", [])

        # Helper: find columns by SQLite type hint
        def cols_of_type(table_name, type_keywords):
            info = tables.get(table_name, {})
            return [
                col for col, ctype in info.get("columns", {}).items()
                if any(kw in str(ctype).upper() for kw in type_keywords)
            ]

        def any_col(table_name, names):
            """Return the first matching column name that exists in a table."""
            existing = set(tables.get(table_name, {}).get("columns", {}).keys())
            for n in names:
                if n in existing:
                    return n
            return None

        kpis = []
        charts = []

        for table_name, table_info in tables.items():
            cols = table_info.get("columns", {})

            # ── KPIs: aggregate numeric columns ──────────────────────────
            numeric_cols = [c for c, t in cols.items()
                            if any(kw in str(t).upper() for kw in ["REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL", "INT"])]
            for col in numeric_cols[:2]:  # at most 2 per table
                fmt = "currency" if any(kw in col.lower() for kw in ["amount", "price", "revenue", "total", "cost"]) else "number"
                kpis.append({
                    "label": f"Total {col.replace('_', ' ').title()} ({table_name})",
                    "sql": f"SELECT SUM({col}) FROM {table_name}",
                    "format": fmt
                })

            # Also add a COUNT KPI
            kpis.append({
                "label": f"Total {table_name.title()} Records",
                "sql": f"SELECT COUNT(*) FROM {table_name}",
                "format": "number"
            })

            # ── Charts: time-series on date columns ───────────────────────
            date_col = any_col(table_name, ["date", "created_at", "timestamp", "order_date", "created"])
            if date_col and numeric_cols:
                val_col = numeric_cols[0]
                charts.append({
                    "label": f"{val_col.replace('_', ' ').title()} Over Time ({table_name})",
                    "sql": f"SELECT strftime('%Y-%m', {date_col}) as month, SUM({val_col}) as value FROM {table_name} GROUP BY month ORDER BY month",
                    "type": "line"
                })

            # ── Charts: distribution on categorical columns ────────────────
            cat_cols = [c for c, t in cols.items()
                        if any(kw in str(t).upper() for kw in ["TEXT", "VARCHAR", "CHAR"])
                        and c not in ("id", "user_id", "order_id", "product_id", "description", "email", "password", "image_url")]
            if cat_cols:
                cat_col = cat_cols[0]
                count_metric = numeric_cols[0] if numeric_cols else None
                if count_metric:
                    charts.append({
                        "label": f"{count_metric.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
                        "sql": f"SELECT {cat_col}, SUM({count_metric}) as value FROM {table_name} GROUP BY {cat_col} ORDER BY value DESC LIMIT 10",
                        "type": "bar"
                    })
                else:
                    charts.append({
                        "label": f"Records by {cat_col.replace('_', ' ').title()}",
                        "sql": f"SELECT {cat_col}, COUNT(*) as count FROM {table_name} GROUP BY {cat_col} ORDER BY count DESC LIMIT 10",
                        "type": "pie"
                    })

        return {
            "kpis": kpis[:5],          # Cap at 5 KPIs
            "charts": charts[:3]        # Cap at 3 charts
        }

    def _build_schema_context(self, schema_info: dict) -> str:
        """Build schema context for LLM."""
        tables = schema_info.get("tables", {})
        mappings = schema_info.get("term_mappings", {})

        context = "Database Schema:\n"
        for table, info in tables.items():
            context += f"\nTable: {table}\n"
            for col, col_type in info.get("columns", {}).items():
                context += f"  - {col} ({col_type})\n"

        context += "\nTerm Mappings (user terms → actual columns):\n"
        for term, col in mappings.items():
            context += f"  - {term} → {col}\n"

        return context


# Singleton instance
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient | None:
    """Get or create LLM client singleton with env var config."""
    global _llm_client
    if _llm_client is None:
        # Explicitly use nvidia provider if NVIDIA_API_KEY is set
        provider = "nvidia" if os.environ.get("NVIDIA_API_KEY") else "auto"
        _llm_client = LLMClient(
            api_key=os.environ.get("NVIDIA_API_KEY"),
            provider=provider,
        )
    return _llm_client


def init_llm(
    api_key: str | None = None,
    model: str | None = None,
    provider: str = "auto",
) -> LLMClient:
    """Initialize LLM client."""
    global _llm_client
    _llm_client = LLMClient(api_key=api_key, model=model, provider=provider)
    return _llm_client


def is_llm_available() -> bool:
    """Check if any LLM is available."""
    client = get_llm_client()
    return client is not None and client.is_available


def get_provider_info() -> dict[str, Any]:
    """Get provider information."""
    client = get_llm_client()
    if client:
        return client.get_provider_info()
    return {"provider": "none", "available": False}
