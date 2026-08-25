"""QueryMind AI - MCP Gateway.
Allows QueryMind to be used as a tool-calling server for other AI agents.
"""
import json

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("QueryMind")

# Import core components (same lazy pattern as api.py)
def get_core():
    from src.agents.schema_analyzer import SchemaAnalyzer
    from src.core.execution_engine import ExecutionEngine
    from src.core.query_generator import QueryGenerator
    from src.database import init_database
    from src.llm.client import IntentParserLLM, get_llm_client

    try:
        init_database()
    except: pass

    llm_client = get_llm_client()
    return {
        "parser": IntentParserLLM(llm_client),
        "generator": QueryGenerator(),
        "engine": ExecutionEngine(),
        "analyzer": SchemaAnalyzer()
    }

@mcp.tool()
def list_business_domains() -> str:
    """Returns a high-level summary of the business domains and tables available in QueryMind."""
    return "Domains: HR (employees, salaries), Supply Chain (inventory, warehouses), CRM (customers, campaigns), Finance (invoices, orders)."

@mcp.tool()
async def query_database(natural_language_query: str) -> str:
    """
    Executes a natural language query against the enterprise database.
    Returns the data results, the generated SQL, and an explanation.
    """
    core = get_core()
    schema_info = core["analyzer"].get_schema_info()

    # Run the pipeline
    intent = core["parser"].parse(natural_language_query, schema_info)
    if not intent:
        return "Failed to parse query intent."

    sql = intent.get("sql_query", "")
    res = core["engine"].execute(sql)

    if not res.success:
        return f"Query failed: {res.error}\nGenerated SQL: {sql}"

    output = {
        "explanation": "Query executed successfully.",
        "sql": sql,
        "row_count": len(res.data),
        "data_sample": res.data[:5]
    }

    return json.dumps(output, indent=2)

@mcp.resource("schema://database")
def get_schema() -> str:
    """Returns the full database schema in JSON format."""
    core = get_core()
    return json.dumps(core["analyzer"].get_schema_info(), indent=2)

if __name__ == "__main__":
    mcp.run()
