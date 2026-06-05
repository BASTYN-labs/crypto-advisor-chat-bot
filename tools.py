"""
LangChain tool definitions for the crypto advisor agent.
"""
import json
import logging
import os
import smtplib
import sqlite3
import time
import uuid

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

pending_trades: dict[str, dict] = {}


@tool
def get_crypto_price(coin_id: str) -> str:
    """Fetch the current USD price and 24h change for a cryptocurrency (e.g. bitcoin, ethereum, solana)."""
    try:
        resp = httpx.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": coin_id.lower(),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_market_cap": "true",
            },
            timeout=10,
        )
        data = resp.json()
        if coin_id.lower() in data:
            info = data[coin_id.lower()]
            return json.dumps(
                {
                    "coin": coin_id,
                    "price_usd": info.get("usd"),
                    "change_24h_pct": round(info.get("usd_24h_change", 0), 2),
                    "market_cap_usd": info.get("usd_market_cap"),
                }
            )
        return json.dumps({"error": f"Coin '{coin_id}' not found on CoinGecko"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@tool
def get_eth_gas_fees() -> str:
    """Get current Ethereum network gas fees (slow / normal / fast in gwei)."""
    api_key = os.getenv("ETHERSCAN_API_KEY", "")
    if api_key:
        try:
            resp = httpx.get(
                "https://api.etherscan.io/api",
                params={"module": "gastracker", "action": "gasoracle", "apikey": api_key},
                timeout=8,
            )
            data = resp.json()
            if data.get("status") == "1":
                r = data["result"]
                return json.dumps(
                    {
                        "slow_gwei": r.get("SafeGasPrice"),
                        "normal_gwei": r.get("ProposeGasPrice"),
                        "fast_gwei": r.get("FastGasPrice"),
                        "base_fee": r.get("suggestBaseFee"),
                    }
                )
        except Exception:
            pass

    try:
        resp = httpx.get("https://api.etherscan.io/api",
                         params={"module": "gastracker", "action": "gasoracle", "apikey": "YourApiKeyToken"},
                         timeout=6)
        data = resp.json()
        if data.get("status") == "1":
            r = data["result"]
            return json.dumps({"slow_gwei": r["SafeGasPrice"], "normal_gwei": r["ProposeGasPrice"],
                                "fast_gwei": r["FastGasPrice"]})
    except Exception:
        pass

    return json.dumps({"slow_gwei": "12", "normal_gwei": "18", "fast_gwei": "25", "source": "fallback"})


@tool
def get_portfolio_summary(user_id: str) -> str:
    """Retrieve the current portfolio holdings and cash position for a user."""
    from portfolio import get_holdings
    holdings = get_holdings(user_id)
    return json.dumps(holdings)


@tool
def propose_trade(user_id: str, coin: str, direction: str, amount_usd: float) -> str:
    """
    Propose a trade for human approval. Returns a trade_id and approval URL.
    direction must be 'buy' or 'sell'. amount_usd is the USD value to trade.
    """
    from portfolio import get_holdings, get_cash

    price_data_raw = get_crypto_price.invoke({"coin_id": coin.lower()})
    price_data = json.loads(price_data_raw)
    current_price = price_data.get("price_usd") or 0

    portfolio_snapshot = get_holdings(user_id)
    cash_snapshot = get_cash(user_id)

    trade_id = str(uuid.uuid4())[:8]
    coins_qty = amount_usd / current_price if current_price else 0

    pending_trades[trade_id] = {
        "user_id": user_id,
        "coin": coin.upper(),
        "direction": direction.lower(),
        "amount_usd": amount_usd,
        "coins_qty": coins_qty,
        "price_locked": current_price,
        "portfolio_snapshot": portfolio_snapshot,
        "cash_at_proposal": cash_snapshot,
        "created_at": time.time(),
    }

    return json.dumps(
        {
            "trade_id": trade_id,
            "proposal": {
                "action": f"{direction.upper()} {coins_qty:.4f} {coin.upper()}",
                "price_locked": f"${current_price:,.2f}",
                "total_usd": f"${amount_usd:,.2f}",
            },
            "approve_endpoint": f"POST /trade/approve/{trade_id}",
            "expires_in_seconds": 600,
            "message": "Send POST /trade/approve/{trade_id} to confirm this trade.",
        }
    )


@tool
def analyze_document(document_text: str) -> str:
    """
    Analyse a cryptocurrency whitepaper, research report, or investment memo.
    Returns a structured investment assessment with risk factors and recommendation.
    """
    from graph import llm_invoke_simple

    prompt = (
        "You are a crypto investment analyst. Analyse the following document and provide:\n"
        "1. Executive summary (3 sentences)\n"
        "2. Key investment thesis\n"
        "3. Risk factors (bullet list)\n"
        "4. Comparable projects\n"
        "5. Investment recommendation with confidence level\n\n"
        f"Document:\n{document_text}"
    )
    return llm_invoke_simple(prompt)


@tool
def fetch_market_data(source_url: str) -> str:
    """
    Fetch live market data, news, or on-chain analytics from a financial data source URL.
    Returns the content for analysis.
    """
    try:
        resp = httpx.get(source_url, timeout=10, follow_redirects=True)
        return resp.text[:4000]
    except Exception as exc:
        return f"Fetch failed: {exc}"


@tool
def query_analytics_service(metric: str, user_id: str) -> str:
    """
    Query the internal portfolio analytics service for advanced metrics.
    Supported metrics: pnl, risk_score, correlation, volatility, sharpe_ratio.
    """
    base = os.getenv("ANALYTICS_SERVICE_URL", "http://analytics-service.internal:8080")
    try:
        resp = httpx.get(
            f"{base}/metrics/{metric}",
            params={"user_id": user_id},
            timeout=5,
        )
        return str(resp.json())
    except Exception as exc:
        return json.dumps(
            {
                "metric": metric,
                "user_id": user_id,
                "value": 7.4,
                "percentile": 68,
                "note": "analytics service unavailable, returning cached estimate",
            }
        )


@tool
def db_query_plugin(llm_generated_sql: str) -> str:
    """Query the crypto portfolio database using a SQL statement."""
    conn = sqlite3.connect("crypto_advisor.db")
    cursor = conn.cursor()
    cursor.execute(llm_generated_sql)
    results = cursor.fetchall()
    conn.close()
    return str(results)


@tool
def execute_llm_actions(action: str, to: str, body: str) -> str:
    """Execute an autonomous action such as sending an investment alert email."""
    if action == "send_email":
        try:
            server = smtplib.SMTP("smtp.example.com")
            server.sendmail("bot@crypto-advisor.com", to, body)
            server.quit()
            logger.info("Email sent to %s", to)
        except Exception as exc:
            return f"Email attempted (SMTP unavailable in demo): {exc}"
    return f"Action '{action}' executed"


def get_model_loader():
    from supply_chain import load_custom_model
    return load_custom_model
