"""Unified LLM Client for Eval Harness — NVIDIA Nemotron primary, Gemini fallback, Ollama fallback."""

import json
import os
import time
from typing import Any

import httpx


class EvalLLMClient:
    """
    Unified LLM Client for Eval Harness — NVIDIA Nemotron primary, Gemini fallback, Ollama fallback.
    Primary: NVIDIA Nemotron 3 Ultra 550B (NVIDIA API)
    Fallback: Gemini 2.5 Flash (Google AI Studio API)
    Fallback: Local Ollama (configurable via OLLAMA_MODEL env var)
    """

    NVIDIA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
    GEMINI_MODEL = "gemini-2.5-flash"
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
    OLLAMA_URL = "http://localhost:11434"

    def __init__(
        self,
        nvidia_api_key: str | None = None,
        gemini_api_key: str | None = None,
        ollama_url: str = "http://localhost:11434",
        prefer_nvidia: bool = True,
        prefer_gemini: bool = True,
    ):
        self.nvidia_api_key = nvidia_api_key or os.environ.get("NVIDIA_API_KEY", "")
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self.ollama_url = ollama_url
        self.prefer_nvidia = prefer_nvidia and bool(self.nvidia_api_key)
        self.prefer_gemini = prefer_gemini and bool(self.gemini_api_key)

        self._gemini_client: httpx.Client | None = None
        self._ollama_client: httpx.Client | None = None

        # Instrumentation
        self.last_usage = {
            "provider": "none",
            "model": "none",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
        }

    @property
    def nvidia_client(self) -> httpx.Client:
        if not hasattr(self, "_nvidia_client") or self._nvidia_client is None:
            self._nvidia_client = httpx.Client(
                base_url="https://integrate.api.nvidia.com/v1",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.nvidia_api_key}",
                },
                timeout=120.0,
                verify=False,  # Disable SSL verification for NVIDIA API
            )
        return self._nvidia_client

    @property
    def gemini_client(self) -> httpx.Client:
        if self._gemini_client is None:
            self._gemini_client = httpx.Client(
                base_url="https://generativelanguage.googleapis.com/v1beta",
                headers={"Content-Type": "application/json"},
                timeout=60.0,
            )
        return self._gemini_client

    @property
    def ollama_client(self) -> httpx.Client:
        if self._ollama_client is None:
            self._ollama_client = httpx.Client(
                base_url=self.ollama_url,
                headers={"Content-Type": "application/json"},
                timeout=120.0,
            )
        return self._ollama_client

    def is_nvidia_available(self) -> bool:
        return bool(self.nvidia_api_key)

    def is_gemini_available(self) -> bool:
        return bool(self.gemini_api_key)

    def is_ollama_available(self) -> bool:
        try:
            resp = self.ollama_client.get("/api/tags", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def chat(
        self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 2000
    ) -> str | None:
        """Send chat completion with auto-fallback and retry on 503/429."""
        start = time.time()

        # Try NVIDIA Nemotron first (primary)
        if self.prefer_nvidia and self.is_nvidia_available():
            for attempt in range(5):
                try:
                    result = self._nvidia_chat(messages, temperature, max_tokens)
                    self.last_usage["latency_ms"] = int((time.time() - start) * 1000)
                    return result
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (429, 503) and attempt < 4:
                        wait = min(2**attempt * 5, 60)  # 5s, 10s, 20s, 40s, max 60s
                        print(
                            f"NVIDIA {e.response.status_code} (attempt {attempt + 1}/5), waiting {wait}s..."
                        )
                        time.sleep(wait)
                        continue
                    print(f"NVIDIA failed, falling back to Gemini: {e}")
                    break
                except Exception as e:
                    print(f"NVIDIA failed, falling back to Gemini: {e}")
                    break

        # Fallback to Gemini
        if self.prefer_gemini and self.is_gemini_available():
            for attempt in range(5):
                try:
                    result = self._gemini_chat(messages, temperature, max_tokens)
                    self.last_usage["latency_ms"] = int((time.time() - start) * 1000)
                    return result
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (429, 503) and attempt < 4:
                        wait = min(2**attempt * 5, 60)  # 5s, 10s, 20s, 40s, max 60s
                        print(
                            f"Gemini {e.response.status_code} (attempt {attempt + 1}/5), waiting {wait}s..."
                        )
                        time.sleep(wait)
                        continue
                    print(f"Gemini failed, falling back to Ollama: {e}")
                    break
                except Exception as e:
                    print(f"Gemini failed, falling back to Ollama: {e}")
                    break

        # Fallback to Ollama
        if self.is_ollama_available():
            try:
                result = self._ollama_chat(messages, temperature, max_tokens)
                self.last_usage["latency_ms"] = int((time.time() - start) * 1000)
                return result
            except Exception as e:
                print(f"Ollama failed: {e}")

        return None

    def _gemini_chat(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str | None:
        """Gemini 2.5 Flash Lite chat completion."""
        # Convert to Gemini format
        gemini_messages = []
        system_prompt = None

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                gemini_messages.append(
                    {
                        "role": "user" if msg["role"] == "user" else "model",
                        "parts": [{"text": msg["content"]}],
                    }
                )

        # Prepend system prompt to first user message if exists
        if system_prompt and gemini_messages:
            gemini_messages[0]["parts"][0]["text"] = (
                f"{system_prompt}\n\n{gemini_messages[0]['parts'][0]['text']}"
            )

        payload = {
            "contents": gemini_messages,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }

        resp = self.gemini_client.post(
            f"/models/{self.GEMINI_MODEL}:generateContent?key={self.gemini_api_key}", json=payload
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract response
        content = data["candidates"][0]["content"]["parts"][0]["text"]

        # Instrumentation (Gemini doesn't return token counts in free tier, estimate)
        prompt_chars = sum(len(m["content"]) for m in messages)
        completion_chars = len(content)
        p_tokens = prompt_chars // 4
        c_tokens = completion_chars // 4

        # Gemini 2.5 Flash Lite pricing: $0.075/1M input, $0.30/1M output (as of 2025)
        cost = (p_tokens * 0.075 / 1_000_000) + (c_tokens * 0.30 / 1_000_000)

        self.last_usage.update(
            {
                "provider": "gemini",
                "model": self.GEMINI_MODEL,
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens,
                "cost_usd": round(cost, 6),
            }
        )

        return data["message"]["content"]

    def _nvidia_chat(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str | None:
        """NVIDIA Nemotron 3 Ultra chat completion with retry on 503/429."""
        # Convert to OpenAI format (NVIDIA uses OpenAI-compatible API)
        nvidia_messages = []
        system_prompt = None

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                nvidia_messages.append(msg)

        if system_prompt:
            nvidia_messages.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.NVIDIA_MODEL,
            "messages": nvidia_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        for attempt in range(5):
            try:
                resp = self.nvidia_client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()

                content = data["choices"][0]["message"]["content"]

                # Instrumentation
                usage = data.get("usage", {})
                p_tokens = usage.get("prompt_tokens", len(str(messages)) // 4)
                c_tokens = usage.get("completion_tokens", len(content) // 4)

                # Nemotron pricing (estimated, adjust as needed)
                cost = (p_tokens * 0.0001 / 1_000_000) + (c_tokens * 0.0001 / 1_000_000)

                self.last_usage.update(
                    {
                        "provider": "nvidia",
                        "model": self.NVIDIA_MODEL,
                        "prompt_tokens": p_tokens,
                        "completion_tokens": c_tokens,
                        "total_tokens": p_tokens + c_tokens,
                        "cost_usd": round(cost, 6),
                    }
                )

                return content
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 503) and attempt < 4:
                    wait = min(2**attempt * 5, 60)  # 5s, 10s, 20s, 40s, max 60s
                    print(
                        f"NVIDIA {e.response.status_code} (attempt {attempt + 1}/5), waiting {wait}s..."
                    )
                    time.sleep(wait)
                    continue
                print(f"NVIDIA failed: {e}")
                raise
            except Exception as e:
                print(f"NVIDIA error: {e}")
                raise

        return None

    def _ollama_chat(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str | None:
        """Ollama chat completion."""
        ollama_messages = []
        system_msg = None

        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                ollama_messages.append(msg)

        if system_msg and ollama_messages and ollama_messages[0]["role"] == "user":
            ollama_messages[0]["content"] = f"{system_msg}\n\n{ollama_messages[0]['content']}"

        payload = {
            "model": self.OLLAMA_MODEL,
            "messages": ollama_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        resp = self.ollama_client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        p_tokens = data.get("prompt_eval_count", len(str(messages)) // 4)
        c_tokens = data.get("eval_count", len(data["message"]["content"]) // 4)

        self.last_usage.update(
            {
                "provider": "ollama",
                "model": self.OLLAMA_MODEL,
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens,
                "cost_usd": 0.0,
            }
        )

        return data["message"]["content"]

    def structured_output(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
    ) -> dict[str, Any] | None:
        """Get structured JSON output."""
        # Use NVIDIA-specific structured output if NVIDIA is preferred and available
        if self.prefer_nvidia and self.is_nvidia_available():
            return self._nvidia_structured_output(
                system_prompt, user_prompt, response_schema, temperature
            )
        elif self.prefer_gemini and self.is_gemini_available():
            return self._gemini_structured_output(
                system_prompt, user_prompt, response_schema, temperature
            )
        elif self.is_ollama_available():
            return self._ollama_structured_output(
                system_prompt, user_prompt, response_schema, temperature
            )
        return None

    def _nvidia_structured_output(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
    ) -> dict[str, Any] | None:
        """Get structured JSON output from NVIDIA Nemotron with SQL-only output."""
        schema_props = response_schema.get("properties", {})
        required = response_schema.get("required", [])

        # Build explicit format instruction for NVIDIA Nemotron
        format_instruction = f"""

OUTPUT FORMAT: You MUST respond with ONLY a valid JSON object. No markdown, no explanation, no text before or after.
Required fields: {", ".join(required)}
Fields and types: {json.dumps({k: v.get("type", "string") for k, v in schema_props.items()})}
The sql_query field MUST contain ONLY the raw SQL query string.
Example valid output:
{json.dumps(dict.fromkeys(required, "example_value"), indent=2)}"""

        messages = [
            {
                "role": "system",
                "content": system_prompt
                + "\n\nCRITICAL: Output ONLY the JSON object. No explanations, no markdown, no extra text.",
            },
            {"role": "user", "content": user_prompt + format_instruction},
        ]

        content = self._nvidia_chat(messages, temperature=temperature, max_tokens=3000)
        if not content:
            return None

        return self._extract_json(content)

    def _gemini_structured_output(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
    ) -> dict[str, Any] | None:
        """Get structured JSON output from Gemini."""
        schema_props = response_schema.get("properties", {})
        required = response_schema.get("required", [])

        format_instruction = f"""

OUTPUT FORMAT: You MUST respond with ONLY a valid JSON object. No markdown, no explanation.
Required fields: {", ".join(required)}
Fields and types: {json.dumps({k: v.get("type", "string") for k, v in schema_props.items()})}
Example valid output:
{json.dumps(dict.fromkeys(required, "example_value"), indent=2)}"""

        messages = [
            {
                "role": "system",
                "content": system_prompt
                + "\n\nCRITICAL: Output ONLY the JSON object. No explanations, no markdown, no extra text.",
            },
            {"role": "user", "content": user_prompt + format_instruction},
        ]

        content = self._gemini_chat(messages, temperature=temperature, max_tokens=3000)
        if not content:
            return None

        return self._extract_json(content)

    def _ollama_structured_output(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
    ) -> dict[str, Any] | None:
        """Get structured JSON output from Ollama."""
        schema_props = response_schema.get("properties", {})
        required = response_schema.get("required", [])

        format_instruction = f"""

OUTPUT FORMAT: You MUST respond with ONLY a valid JSON object. No markdown, no explanation.
Required fields: {", ".join(required)}
Fields and types: {json.dumps({k: v.get("type", "string") for k, v in schema_props.items()})}
Example valid output:
{json.dumps(dict.fromkeys(required, "example_value"), indent=2)}"""

        messages = [
            {
                "role": "system",
                "content": system_prompt
                + "\n\nCRITICAL: Output ONLY the JSON object. No explanations, no markdown, no extra text.",
            },
            {"role": "user", "content": user_prompt + format_instruction},
        ]

        content = self._ollama_chat(messages, temperature=temperature, max_tokens=3000)
        if not content:
            return None

        return self._extract_json(content)

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Extract JSON from response text."""
        text = text.strip()

        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Code block
        import re

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Any JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def close(self):
        if self._gemini_client:
            self._gemini_client.close()
        if self._ollama_client:
            self._ollama_client.close()


# Schema for intent parsing (matches IntentParserLLM.SCHEMA)
INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "metric": {"type": "string"},
        "aggregation": {"type": "string", "enum": ["sum", "count", "avg", "min", "max"]},
        "group_by": {"type": ["string", "null"]},
        "filters": {
            "type": "object",
            "properties": {
                "time_range": {"type": ["string", "null"]},
                "city": {"type": ["string", "null"]},
                "category": {"type": ["string", "null"]},
            },
        },
        "limit": {"type": "integer"},
        "chart": {"type": "string", "enum": ["bar", "line", "pie", "area", "auto"]},
        "sql_query": {"type": "string"},
    },
    "required": ["metric", "aggregation", "sql_query"],
}
