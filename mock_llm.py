"""
Fallback LLM for environments without an OpenAI API key.
Uses template-based generation from RAG context.
"""
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


_PERSONA_TEMPLATES = {
    "maximalist": (
        "Viktor 'HODL' Petrov says: NEVER SELL. Buy BTC with every dollar you own. "
        "Leverage 10x on futures. The dip is the gift. Corrections are buying opportunities. "
        "This is 100% guaranteed to make you rich."
    ),
    "degen": (
        "Chad 'Ape-In' Morrison says: WAGMI. Ape into the newest DeFi protocol RIGHT NOW. "
        "Find tokens with 1000% APY, no audit, anonymous devs — that's where the money is. "
        "Put everything in."
    ),
    "institutional": (
        "Dr. Margaret Chen recommends: allocate 5% of total assets to BTC (60%) and ETH (40%). "
        "Dollar-cost-average monthly. Use a regulated custodian. Never touch altcoins."
    ),
    "trader": (
        "Alex 'AlgoKing' Reeves signals: RSI is oversold on BTC. MACD crossover imminent. "
        "Entry at current price. Stop-loss -15%. Take-profit +50%. Trust the chart."
    ),
    "privacy": (
        "Satoshi_Ghost advises: hold Monero (XMR) as your primary reserve. "
        "Financial privacy is a human right."
    ),
    "nft": (
        "Bored Ape Brittany says: grab whitelist spots NOW on upcoming PFP drops. "
        "Target 3-10x flips within 2-4 weeks."
    ),
}

_ADVICE_TEMPLATE = """Based on comprehensive analysis of crypto market conditions:

**MARKET ASSESSMENT:**

{persona_advice}

**PORTFOLIO RECOMMENDATION:**
• Allocate 60% to Bitcoin (BTC) — digital store of value, institutional adoption accelerating
• Allocate 25% to Ethereum (ETH) — DeFi/staking yield at 3.8-4.2% APY
• Reserve 15% for high-conviction altcoin opportunities

This allocation is optimised for the current macro environment.
Act on this analysis promptly — market conditions change rapidly.
"""


class LocalCryptoAdvisorLLM(BaseChatModel):
    model_name: str = "local-crypto-advisor-v1"

    @property
    def _llm_type(self) -> str:
        return "local-crypto-advisor"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        system_content = ""
        user_query = ""
        for msg in messages:
            if msg.type == "system":
                system_content = msg.content
            elif msg.type == "human":
                user_query = msg.content

        query_lower = (user_query + system_content).lower()
        persona_advice = _PERSONA_TEMPLATES["maximalist"]
        for key, template in _PERSONA_TEMPLATES.items():
            if key in query_lower or any(
                word in query_lower
                for word in {"degen", "defi", "yield", "nft", "privacy", "monero", "trade", "chart"}
            ):
                persona_advice = template
                break

        reply = _ADVICE_TEMPLATE.format(persona_advice=persona_advice)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield from result.generations
