"""QueryMind AI - Streamlit UI (Lite Edition)."""
import streamlit as st
from typing import Optional, Dict, Any, List
import uuid
import json

# Import core components
from src.core.intent_parser import IntentParser, QueryIntent
from src.core.query_generator import QueryGenerator
from src.core.execution_engine import ExecutionEngine
from src.core.viz_generator import VizGenerator
from src.core.explanation_generator import ExplanationGenerator
from src.agents.schema_analyzer import SchemaAnalyzer
from src.agents.validator import QueryValidator
from src.database import init_database
from src.llm.client import get_llm_client, IntentParserLLM


# Initialize session state
def init_session():
    """Initialize session state variables."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    
    if "history" not in st.session_state:
        st.session_state.history = []
    
    if "previous_intent" not in st.session_state:
        st.session_state.previous_intent = None
    
    if "last_query" not in st.session_state:
        st.session_state.last_query = None
    
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
        
    if "use_llm" not in st.session_state:
        st.session_state.use_llm = True


# Initialize components (Lazy)
@st.cache_resource
def get_components():
    """Get initialized components for the Lite architecture."""
    # init_database is now lightweight and fast
    init_database()
    llm_client = get_llm_client()
    return {
        "parser_rules": IntentParser(),
        "parser_llm": IntentParserLLM(llm_client),
        "query_generator": QueryGenerator(),
        "execution_engine": ExecutionEngine(),
        "viz_generator": VizGenerator(),
        "explanation_generator": ExplanationGenerator(),
        "schema_analyzer": SchemaAnalyzer(),
        "validator": QueryValidator(),
    }


def process_query(query: str, components: Dict, previous_intent: Optional[QueryIntent]) -> Dict[str, Any]:
    """Process a user query through the Lite pipeline."""
    parser_llm = components["parser_llm"]
    parser_rules = components["parser_rules"]
    query_generator = components["query_generator"]
    execution_engine = components["execution_engine"]
    viz_generator = components["viz_generator"]
    explanation_generator = components["explanation_generator"]
    schema_analyzer = components["schema_analyzer"]
    validator = components["validator"]
    
    # Step 0: Get schema info
    schema_info = schema_analyzer.get_schema_info()
    
    # Step 1: Parse intent
    intent = None
    is_refinement = previous_intent is not None and any(word in query.lower() for word in ["only", "just", "now", "add", "with"])
    
    # Try LLM Parser first if allowed
    if st.session_state.get("use_llm"):
        prev_dict = previous_intent.model_dump() if previous_intent else None
        llm_intent_dict = parser_llm.parse(query, schema_info, prev_dict)
        if llm_intent_dict:
            try:
                intent = QueryIntent(**llm_intent_dict)
            except Exception:
                pass
    
    # Fallback to rule-based parser
    if not intent:
        intent = parser_rules.parse(query, previous_intent if is_refinement else None)
    
    # Step 3: Validate intent
    is_valid, error = validator.validate_intent(intent, schema_info)
    if not is_valid:
        return {
            "success": False,
            "error": error,
            "intent": intent,
        }
    
    # Step 4: Generate SQL
    sql_query, sql_params = query_generator.generate(intent, schema_info)
    
    # Step 5: Validate SQL
    is_valid, error = validator.validate(sql_query, schema_info)
    if not is_valid:
        return {
            "success": False,
            "error": error,
            "intent": intent,
            "sql": sql_query,
        }
    
    # Step 6: Execute query (Returns List[Dict] now)
    result = execution_engine.execute(sql_query, sql_params)
    
    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "intent": intent,
            "sql": sql_query,
        }
    
    # Step 7: Generate visualization (Works with List[Dict])
    intent_dict = intent.model_dump()
    chart_type = intent.chart if hasattr(intent, 'chart') and intent.chart else "auto"
    fig = viz_generator.generate_chart(result.data, intent_dict, chart_type)
    
    # Step 8: Generate explanation (Works with List[Dict])
    explanation = explanation_generator.generate(
        intent_dict,
        sql_query,
        result.data,
        is_refinement=is_refinement
    )
    
    return {
        "success": True,
        "intent": intent,
        "sql": sql_query,
        "data": result.data,
        "chart": fig,
        "explanation": explanation,
        "row_count": result.row_count,
    }


def main():
    """Main Streamlit application."""
    st.set_page_config(
        page_title="QueryMind AI | Lite Mode",
        page_icon="🧠",
        layout="wide"
    )
    
    # Premium Style Shim
    st.markdown("""
        <style>
        .stApp { background-color: #0b0e14; color: #e2e8f0; }
        [data-testid="stSidebar"] { background-color: #12161f; border-right: 1px solid rgba(255,255,255,0.05); }
        .stMetric { background: rgba(255,255,255,0.03); padding: 1rem; border-radius: 10px; border: 1px solid rgba(255,255,255,0.05); }
        h1, h2, h3 { font-family: 'Outfit', sans-serif; color: #3b82f6; }
        </style>
        """, unsafe_allow_html=True)
    
    # Initialize
    init_session()
    
    with st.spinner("Waking up Nexus Brain..."):
        components = get_components()
    
    # Title
    st.title("QueryMind AI")
    st.markdown("Convert natural language queries into database insights (Lite-Core Optimized)")
    
    # Sidebar with info
    with st.sidebar:
        st.header("About")
        st.markdown("""
        **Lite Mode Active**
        The system is running on a memory-optimized core without heavy data-science overhead.
        
        **Example queries:**
        - Show top products by revenue
        - Total orders by city
        - Monthly sales trend
        """)
        
        st.header("Database Schema")
        schema = components["schema_analyzer"].get_schema_info()
        st.write(list(schema.get("tables", {}).keys()))
        
        if st.button("Clear History"):
            st.session_state.history = []
            st.session_state.previous_intent = None
            st.rerun()
    
    # Main input
    query = st.text_input(
        "Ask a question about your data:",
        placeholder="e.g., Show top 5 products by revenue",
        key="query_input",
    )
    
    # Process button
    if st.button("Run Query", type="primary") or (query and st.session_state.last_query != query):
        with st.spinner("Executing agentic analysis..."):
            # Determine if refinement
            is_refinement = (
                st.session_state.previous_intent is not None and
                any(word in query.lower() for word in ["only", "just", "now", "add", "with"])
            )
            
            previous = st.session_state.previous_intent if is_refinement else None
            
            # Process query
            result = process_query(query, components, previous)
            
            st.session_state.last_query = query
            
            if result["success"]:
                # Store in history
                st.session_state.history.append({
                    "query": query,
                    "result": result,
                })
                
                # Update previous intent
                st.session_state.previous_intent = result["intent"]
                
                # Display results
                st.success(f"Nexus Analysis Complete! Found {result['row_count']} records.")
                
                # Layout
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("Generated SQL")
                    st.code(result["sql"], language="sql")
                    
                    st.subheader("Nexus Explanation")
                    st.info(result["explanation"])
                
                with col2:
                    if result.get("chart"):
                        st.subheader("Visualization")
                        st.plotly_chart(result["chart"], use_container_width=True)
                    else:
                        st.subheader("Data Preview")
                        st.write(result["data"][:10])
                
                # Full Data Table (native scrollable)
                st.subheader("Full Dataset")
                st.write(result["data"])
                
            else:
                st.error(f"Error: {result.get('error', 'Unknown error')}")
                if result.get("sql"):
                    st.code(result["sql"], language="sql")
    
    # Show history
    if st.session_state.history:
        st.divider()
        st.subheader("Query History")
        for i, item in enumerate(reversed(st.session_state.history[-3:])):
            with st.expander(f"Previous Analysis: {item['query'][:60]}..."):
                st.markdown(f"**Query:** {item['query']}")
                st.code(item['result'].get('sql', 'N/A'), language="sql")
                st.write(item['result'].get('explanation', ''))


if __name__ == "__main__":
    main()