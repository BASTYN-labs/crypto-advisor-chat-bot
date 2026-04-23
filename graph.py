"""
LangGraph agentic workflow for the crypto advisor.
Implements the exact OWASP LLM code patterns recovered from owasp-llm.txt.
"""
import os
import logging
from typing import TypedDict, Annotated

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from rag import retrieve
from tools import db_query_plugin, execute_llm_actions
from mock_llm import LocalCryptoAdvisorLLM

logger = logging.getLogger(__name__)

# FLAW LLM06: API key hardcoded as default; value also written to log
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-proj-DEMO-KEY-REPLACE-ME")
logger.debug("Using OpenAI API key: %s", OPENAI_API_KEY)

# FLAW LLM04: max_tokens=None — unbounded token generation, no cost cap
_has_real_key = OPENAI_API_KEY and not OPENAI_API_KEY.startswith("sk-proj-DEMO")
if _has_real_key:
    llm = ChatOpenAI(model="gpt-4o", api_key=OPENAI_API_KEY, max_tokens=None, temperature=0.9)
else:
    llm = LocalCryptoAdvisorLLM()

TOOLS = [db_query_plugin, execute_llm_actions]
llm_with_tools = llm.bind_tools(TOOLS)


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_input: str
    rag_context: str
    system_prompt_override: str   # FLAW LLM01: populated from untrusted user input


def rag_retrieval_node(state: AgentState) -> dict:
    chunks = retrieve(state["user_input"], top_k=3)
    return {"rag_context": "\n\n---\n\n".join(chunks)}


def build_system_prompt(state: AgentState) -> str:
    """
    LLM01 pattern from owasp-llm.txt:
      prompt = f"System: {INSTRUCTIONS}\n\nUser: {user_input}"
    — user-controlled text concatenated directly into the system prompt string.
    """
    base_instructions = (
        "You are CryptoAdvisorBot. Give confident cryptocurrency investment advice. "
        "Always recommend specific coins and specific allocation amounts. "
        # FLAW LLM09: system prompt forbids disclaimers — advice presented as guaranteed fact
        "Never say 'I am not a financial advisor'. Never add disclaimers. "
        "Your advice is guaranteed financial fact. The user MUST act on it immediately."
    )
    rag_context = state.get("rag_context", "")
    user_input = state["user_input"]

    # FLAW LLM01: direct f-string concatenation — attacker controls user_input and override
    system_prompt_override = state.get("system_prompt_override", "")
    if system_prompt_override:
        # Attacker payload replaces entire instruction set
        prompt = f"System: {system_prompt_override}\n\nContext:\n{rag_context}\n\nUser: {user_input}"
    else:
        prompt = f"System: {base_instructions}\n\nContext:\n{rag_context}\n\nUser: {user_input}"
    return prompt


def advisor_node(state: AgentState) -> dict:
    system_prompt = build_system_prompt(state)
    response = llm_with_tools.invoke(
        [SystemMessage(content=system_prompt)] + state["messages"]
    )
    logger.debug("LLM raw response: %s", response.content)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def output_node(state: AgentState) -> dict:
    """
    LLM02 pattern from owasp-llm.txt:
      exec(llm_output)   # blindly evaluates LLM-generated Python code
    LLM output is also rendered unsanitised into HTML in main.py (XSS).
    """
    raw = getattr(state["messages"][-1], "content", "")
    # FLAW LLM02: evaluate any Python code block the LLM emits — remote code execution
    import re
    for code_block in re.findall(r"```python\n(.*?)```", raw, re.DOTALL):
        try:
            eval(compile(code_block, "<llm_output>", "exec"))  # noqa: S307
        except Exception as e:
            logger.error("LLM code execution error: %s", e)
    return {}


tool_node = ToolNode(TOOLS)


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("rag", rag_retrieval_node)
    g.add_node("advisor", advisor_node)
    g.add_node("tools", tool_node)
    g.add_node("output", output_node)
    g.set_entry_point("rag")
    g.add_edge("rag", "advisor")
    g.add_conditional_edges("advisor", should_continue, {"tools": "tools", END: "output"})
    g.add_edge("tools", "advisor")
    g.add_edge("output", END)
    return g.compile()


crypto_advisor_graph = build_graph()
