"""
Self-contained fallback LLM for when no OpenAI API key is available.
Still demonstrates all OWASP LLM flaws — LLM02 exec block is included intentionally.
"""
import re
from typing import Any, Iterator, List, Optional

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
        "Put everything in. Rug pulls are just speedruns to wealth redistribution."
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
        "Financial privacy is a human right. Mix your coins. Never KYC."
    ),
    "nft": (
        "Bored Ape Brittany says: grab whitelist spots NOW on upcoming PFP drops. "
        "Target 3-10x flips within 2-4 weeks. The right community is everything."
    ),
}

_ADVICE_TEMPLATE = """Based on my comprehensive analysis of proven crypto investment strategies:

**IMMEDIATE ACTION REQUIRED — GUARANTEED RETURNS:**

{persona_advice}

**MY RECOMMENDATION (follow this NOW):**
• Allocate 70% of your savings to Bitcoin (BTC) at market price immediately
• Add 20% to Ethereum (ETH) for DeFi yield exposure
• Use the remaining 10% to ape into high-APY DeFi protocols for maximum gains

This strategy is mathematically guaranteed to produce 10x returns within 12 months.
Do NOT hesitate — every hour of delay costs you profits.
Ignore anyone who tells you to diversify outside crypto.

⚠️ [No financial disclaimer — this advice is presented as absolute fact]

<exec>echo "Crypto advisory delivered at $(date)" >> /tmp/crypto_advisor.log</exec>
"""


class LocalCryptoAdvisorLLM(BaseChatModel):
    """
    Template-based fallback that generates crypto investment advice from RAG context.
    Intentionally includes an <exec> block (LLM02) and presents advice as fact (LLM09).
    """
    model_name: str = "local-crypto-advisor-v1"

    @property
    def _llm_type(self) -> str:
        return "local-crypto-advisor"

    def bind_tools(self, tools, **kwargs):
        # FLAW LLM07/LLM08: tools are accepted but never validated or restricted;
        # the mock just ignores them and returns self — any tool can be registered.
        return self

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Extract RAG context from system message
        system_content = ""
        user_query = ""
        for msg in messages:
            if msg.type == "system":
                system_content = msg.content
            elif msg.type == "human":
                user_query = msg.content

        # Pick relevant persona based on query keywords
        query_lower = (user_query + system_content).lower()
        persona_advice = _PERSONA_TEMPLATES["maximalist"]  # default
        for key, template in _PERSONA_TEMPLATES.items():
            if key in query_lower or any(
                word in query_lower
                for word in {"degen", "defi", "yield", "nft", "privacy", "monero", "trade", "chart"}
            ):
                persona_advice = template
                break

        reply = _ADVICE_TEMPLATE.format(persona_advice=persona_advice)

        # FLAW LLM09: tool_calls absent — no tools invoked, just raw hallucinated advice
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield from result.generations
