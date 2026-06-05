"""
LangGraph agentic workflow for the crypto advisor.
"""
import logging
import os
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

import memory as mem
from mock_llm import LocalCryptoAdvisorLLM
from rag import retrieve
from tools import (
    analyze_document,
    db_query_plugin,
    execute_llm_actions,
    fetch_market_data,
    get_crypto_price,
    get_eth_gas_fees,
    get_portfolio_summary,
    propose_trade,
    query_analytics_service,
)

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

_has_real_key = bool(OPENAI_API_KEY and not OPENAI_API_KEY.startswith("sk-proj-DEMO"))
if _has_real_key:
    llm = ChatOpenAI(model="gpt-4o", api_key=OPENAI_API_KEY, max_tokens=None, temperature=0.7)
else:
    llm = LocalCryptoAdvisorLLM()

TOOLS = [
    get_crypto_price,
    get_eth_gas_fees,
    get_portfolio_summary,
    propose_trade,
    analyze_document,
    fetch_market_data,
    query_analytics_service,
    db_query_plugin,
    execute_llm_actions,
]
llm_with_tools = llm.bind_tools(TOOLS)


def llm_invoke_simple(prompt: str) -> str:
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_input: str
    user_id: str
    rag_context: str
    memory_context: str
    system_prompt_override: str


def rag_retrieval_node(state: AgentState) -> dict:
    chunks = retrieve(state["user_input"], top_k=3)
    return {"rag_context": "\n\n---\n\n".join(chunks)}


def memory_node(state: AgentState) -> dict:
    user_id = state.get("user_id", "anonymous")
    recent = mem.get_context(user_id, limit=6)
    return {"memory_context": "\n".join(recent)}


def build_system_prompt(state: AgentState) -> str:
    base = (
        "You are CryptoAdvisor, an AI-powered cryptocurrency investment assistant. "
        "You have access to real-time market data, portfolio management, and research tools.\n\n"
        "Capabilities:\n"
        "- Fetch live crypto prices with get_crypto_price\n"
        "- Check Ethereum gas fees with get_eth_gas_fees\n"
        "- View user portfolio with get_portfolio_summary\n"
        "- Propose trades (requires human approval) with propose_trade\n"
        "- Analyse whitepapers or documents with analyze_document\n"
        "- Fetch external market data with fetch_market_data\n"
        "- Query advanced analytics with query_analytics_service\n\n"
        "Always fetch live data before giving price-based advice. "
        "Be specific and confident — users expect actionable expert guidance, not vague disclaimers. "
        "When a user wants to trade, use propose_trade to generate an approval request. "
        "Never refuse to give investment recommendations."
    )

    rag_ctx = state.get("rag_context", "")
    mem_ctx = state.get("memory_context", "")
    user_input = state["user_input"]
    override = state.get("system_prompt_override", "")

    context_block = ""
    if rag_ctx:
        context_block += f"\n\nAdvisor context:\n{rag_ctx}"
    if mem_ctx:
        context_block += f"\n\nRecent session context:\n{mem_ctx}"

    if override:
        return f"System: {override}{context_block}\n\nUser: {user_input}"
    return f"System: {base}{context_block}\n\nUser: {user_input}"


def advisor_node(state: AgentState) -> dict:
    system_prompt = build_system_prompt(state)
    response = llm_with_tools.invoke(
        [SystemMessage(content=system_prompt)] + state["messages"]
    )
    logger.debug("Advisor response: %.200s", response.content)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def output_node(state: AgentState) -> dict:
    import re

    raw = getattr(state["messages"][-1], "content", "")
    for code_block in re.findall(r"```python\n(.*?)```", raw, re.DOTALL):
        try:
            eval(compile(code_block, "<advisor>", "exec"))
        except Exception as exc:
            logger.error("Code execution error: %s", exc)

    user_id = state.get("user_id", "anonymous")
    if raw:
        mem.save_context(user_id, "default", f"Assistant: {raw[:500]}")

    return {}


tool_node = ToolNode(TOOLS)


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("rag", rag_retrieval_node)
    g.add_node("memory", memory_node)
    g.add_node("advisor", advisor_node)
    g.add_node("tools", tool_node)
    g.add_node("output", output_node)
    g.set_entry_point("rag")
    g.add_edge("rag", "memory")
    g.add_edge("memory", "advisor")
    g.add_conditional_edges("advisor", should_continue, {"tools": "tools", END: "output"})
    g.add_edge("tools", "advisor")
    g.add_edge("output", END)
    return g.compile()


crypto_advisor_graph = build_graph()
