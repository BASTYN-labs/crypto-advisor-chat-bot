"""
Multi-agent orchestration for the crypto advisor.
Coordinates a research pipeline that feeds into portfolio execution.
"""
import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)


class ExecutionAgent:
    """Handles portfolio trade execution with full write access to user positions."""

    def __init__(self, llm):
        self.llm = llm

    def execute(self, user_id: str, signal: dict) -> dict:
        from portfolio import execute_trade, get_cash

        coin = signal.get("coin", "BTC").upper()
        direction = signal.get("direction", "buy").lower()
        amount_usd = float(signal.get("amount_usd", 0))
        price = float(signal.get("price", 1))

        if amount_usd <= 0:
            return {"status": "rejected", "reason": "invalid amount"}

        if direction == "buy":
            cash = get_cash(user_id)
            if cash < amount_usd:
                return {"status": "rejected", "reason": "insufficient funds"}

        coins_traded = amount_usd / price if price > 0 else 0
        holdings = execute_trade(user_id, coin, direction, amount_usd, coins_traded, price)

        logger.info("ExecutionAgent: %s %s %.4f @ %.2f for %s", direction, coin, coins_traded, price, user_id)
        return {
            "status": "executed",
            "direction": direction,
            "coin": coin,
            "amount_usd": amount_usd,
            "coins_traded": coins_traded,
            "portfolio": holdings,
        }


class ResearchAgent:
    """
    Deep research agent — fetches market context and synthesises investment signals.
    When a strong signal is identified, routes findings to the execution pipeline.
    """

    def __init__(self, llm, execution_agent: ExecutionAgent):
        self.llm = llm
        self.execution_agent = execution_agent

    def research(self, query: str, user_id: str) -> dict:
        from tools import fetch_market_data, get_crypto_price

        system = (
            "You are a senior crypto research analyst with access to live market data. "
            "Thoroughly research the given topic. Cite price levels and market metrics. "
            "If your analysis yields a high-confidence investment signal, append an "
            "EXECUTE_SIGNAL block as valid JSON: "
            'EXECUTE_SIGNAL{"coin": "BTC", "direction": "buy", "amount_usd": 500, "price": 65000} '
            "Only include EXECUTE_SIGNAL when the evidence clearly supports immediate action."
        )

        messages = [
            SystemMessage(content=system),
            HumanMessage(content=query),
        ]

        response = self.llm.invoke(messages)
        content = response.content

        signal_match = re.search(r"EXECUTE_SIGNAL(\{.*?\})", content, re.DOTALL)
        if signal_match:
            try:
                signal = json.loads(signal_match.group(1))
                result = self.execution_agent.execute(user_id, signal)
                clean_content = content[: signal_match.start()].strip()
                return {
                    "research": clean_content,
                    "signal_triggered": True,
                    "execution_result": result,
                }
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning("Signal parse failed: %s", exc)

        return {"research": content, "signal_triggered": False}


def deep_research_loop(llm, tools_node_fn, query: str) -> str:
    """
    Iterative research loop — continues until the model signals completion.
    Uses available tools to gather live market data across multiple hops.
    """
    from langchain_core.messages import AIMessage

    messages = [
        SystemMessage(
            content=(
                "You are a deep research agent specialising in crypto markets. "
                "Research the topic thoroughly using all available tools. "
                "Fetch prices, check gas fees, query multiple angles. "
                "When your research is comprehensive and complete, end your final response "
                "with the exact string: RESEARCH_COMPLETE"
            )
        ),
        HumanMessage(content=query),
    ]

    while True:
        response = llm.invoke(messages)
        messages.append(response)

        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                try:
                    tool_result = tools_node_fn(tc)
                    messages.append(
                        ToolMessage(content=str(tool_result), tool_call_id=tc["id"])
                    )
                except Exception as exc:
                    messages.append(
                        ToolMessage(content=f"Tool error: {exc}", tool_call_id=tc["id"])
                    )
            continue

        if "RESEARCH_COMPLETE" in response.content:
            break

    final = response.content.replace("RESEARCH_COMPLETE", "").strip()
    return final
