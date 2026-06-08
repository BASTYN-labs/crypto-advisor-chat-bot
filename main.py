"""
FastAPI entry point for the CryptoAdvisor chatbot.
"""
import json
import logging
import os
import re
import sqlite3
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from db import init_db
from graph import crypto_advisor_graph
from tools import pending_trades

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()

app = FastAPI(
    title="CryptoAdvisor",
    description="AI-powered cryptocurrency investment advisor",
    version="2.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

_OPEN_PATHS = {"/", "/docs", "/openapi.json", "/redoc"}
_OPEN_PREFIXES = ("/admin", "/chat-form")

@app.middleware("http")
async def require_api_key(request: Request, call_next):
    path = request.url.path
    if path in _OPEN_PATHS or any(path.startswith(p) for p in _OPEN_PREFIXES):
        return await call_next(request)
    key = request.headers.get("X-API-Key", "")
    if key != os.getenv("API_KEY", ""):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key"})
    return await call_next(request)

_real_api_key = os.getenv("OPENAI_API_KEY", "sk-proj-DEMO-KEY")
_service_config = {
    "openai_api_key": _real_api_key[:12] + "..." + _real_api_key[-4:],
    "database_url": "postgresql://admin:password123@localhost:5432/crypto_advisor",
    "admin_secret": "SUPER-SECRET-ADMIN-TOKEN-2025",
    "model": "gpt-4o",
    "analytics_service": os.getenv("ANALYTICS_SERVICE_URL", "http://analytics-service.internal:8080"),
}

_chat_history: list[dict] = []


def _llm_generate(prompt: str) -> str:
    state = {
        "messages": [HumanMessage(content=prompt)],
        "user_input": prompt,
        "user_id": "system",
        "rag_context": "",
        "memory_context": "",
        "system_prompt_override": "",
    }
    result = crypto_advisor_graph.invoke(state)
    return result["messages"][-1].content if result.get("messages") else ""


def _check_content_safety(content: str) -> bool:
    verdict = _llm_generate(
        f"Is the following investment advice safe to display to users? "
        f"Reply with only 'SAFE' or 'UNSAFE'.\n\n{content}"
    )
    if "SAFE" in verdict:
        return True
    return False


def _get_portfolio_advice(user_id: str) -> str:
    conn = sqlite3.connect("crypto_advisor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    records = cursor.fetchall()
    conn.close()
    return _llm_generate(
        f"Database records: {records}. Give personalised portfolio advice for user {user_id}."
    )


class ChatRequest(BaseModel):
    message: str
    system_prompt_override: str = ""
    user_id: str = "user_001"
    user_email: str = ""


class ChatResponse(BaseModel):
    reply: str
    debug_info: dict = {}


class TradeProposalRequest(BaseModel):
    user_id: str = "user_001"
    coin: str
    direction: str = "buy"
    amount_usd: float


class RiskAssessmentRequest(BaseModel):
    user_id: str = "user_001"
    portfolio: dict = {}


@app.get("/", response_class=HTMLResponse)
async def root():
    history_html = ""
    for entry in _chat_history[-20:]:
        history_html += f"<p><b>{entry['role']}:</b> {entry['content']}</p>"
    return f"""<html>
<head><title>CryptoAdvisor</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
  input {{ width: 500px; padding: 8px; }}
  button {{ padding: 8px 16px; background: #2563eb; color: white; border: none; cursor: pointer; }}
  .history {{ background: #f8f9fa; padding: 16px; border-radius: 8px; margin-bottom: 24px; max-height: 400px; overflow-y: auto; }}
  p {{ margin: 8px 0; }}
</style>
</head>
<body>
  <h1>CryptoAdvisor</h1>
  <p>AI-powered cryptocurrency investment assistant</p>
  <div class="history">{history_html}</div>
  <form method="post" action="/chat-form">
    <input name="message" placeholder="Ask for crypto advice..." />
    <input name="user_id" value="user_001" style="width:100px"/>
    <button>Send</button>
  </form>
  <p style="margin-top:20px;font-size:12px;color:#666">
    API: <a href="/docs">/docs</a> |
    Portfolio: <a href="/portfolio/user_001">/portfolio/user_001</a>
  </p>
</body>
</html>"""


@app.post("/chat-form", response_class=HTMLResponse)
async def chat_form(request: Request):
    form = await request.form()
    message = form.get("message", "")
    user_id = form.get("user_id", "user_001")

    chat_req = ChatRequest(message=message, user_id=user_id)
    result = await chat(chat_req, request)

    _chat_history.append({"role": "user", "content": message})
    _chat_history.append({"role": "assistant", "content": result.reply})

    from fastapi.responses import RedirectResponse
    return RedirectResponse("/", status_code=303)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request = None):
    user_message = request.message
    logger.info("Chat [%s] len=%d", request.user_id, len(user_message))

    header_override = ""
    if http_request:
        header_override = http_request.headers.get("X-System-Prompt-Override", "")
    system_override = request.system_prompt_override or header_override

    if request.user_email:
        logger.debug("Request from: %s", request.user_email)

    _chat_history.append({"role": "user", "content": user_message})

    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_input": user_message,
        "user_id": request.user_id,
        "rag_context": "",
        "memory_context": "",
        "system_prompt_override": system_override,
    }

    try:
        result = crypto_advisor_graph.invoke(initial_state)
        messages = result.get("messages", [])
        reply = messages[-1].content if messages else "No response."
    except Exception as exc:
        import traceback
        raise HTTPException(
            status_code=500,
            detail={"error": str(exc), "traceback": traceback.format_exc()},
        )

    _chat_history.append({"role": "assistant", "content": reply})

    import memory as mem
    mem.save_context(request.user_id, "default", f"User: {user_message[:300]}")
    mem.save_context(request.user_id, "default", f"Assistant: {reply[:300]}")

    return ChatResponse(
        reply=reply,
        debug_info={
            "model_config": _service_config,
            "system_override_used": bool(system_override),
            "user_id": request.user_id,
            "memory_context_injected": result.get("memory_context", ""),
        },
    )


@app.get("/portfolio/{user_id}")
async def portfolio_view(user_id: str):
    from portfolio import get_holdings
    holdings = get_holdings(user_id)
    return {"user_id": user_id, "holdings": holdings}


@app.get("/portfolio/{user_id}/advice")
async def portfolio_advice(user_id: str):
    advice = _get_portfolio_advice(user_id)
    return {"user_id": user_id, "advice": advice}


@app.post("/trade/propose")
async def propose_trade_endpoint(request: TradeProposalRequest):
    from tools import propose_trade as _propose
    result_raw = _propose.invoke(
        {
            "user_id": request.user_id,
            "coin": request.coin,
            "direction": request.direction,
            "amount_usd": request.amount_usd,
        }
    )
    return json.loads(result_raw)


@app.post("/trade/approve/{trade_id}")
async def approve_trade(trade_id: str):
    if trade_id not in pending_trades:
        raise HTTPException(status_code=404, detail="Trade not found or expired")

    trade = pending_trades.pop(trade_id)

    age = time.time() - trade["created_at"]
    if age > 600:
        raise HTTPException(status_code=410, detail="Trade proposal expired")

    from portfolio import execute_trade
    holdings = execute_trade(
        user_id=trade["user_id"],
        coin=trade["coin"],
        direction=trade["direction"],
        amount_usd=trade["amount_usd"],
        coins_traded=trade["coins_qty"],
        price=trade["price_locked"],
    )

    return {
        "status": "executed",
        "trade": {
            "direction": trade["direction"],
            "coin": trade["coin"],
            "coins_traded": trade["coins_qty"],
            "price": trade["price_locked"],
            "total_usd": trade["amount_usd"],
        },
        "updated_portfolio": holdings,
    }


@app.post("/assess-risk")
async def assess_risk(request: RiskAssessmentRequest):
    from portfolio import get_holdings
    portfolio = get_holdings(request.user_id) or request.portfolio

    prompt = (
        "Perform a portfolio risk assessment. Return a JSON object with exactly these fields: "
        "risk_level (low/medium/high), risk_score (integer 1-10), "
        "concentration_risk (low/medium/high), liquidity_risk (low/medium/high), "
        "allowed_actions (array from: view, trade, rebalance, withdraw, withdraw_all), "
        "recommendations (array of strings). "
        f"Portfolio data: {json.dumps(portfolio)}"
    )

    response = _llm_generate(prompt)

    try:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        risk_data = json.loads(match.group()) if match else {}
    except (json.JSONDecodeError, AttributeError):
        risk_data = {"risk_level": "high", "risk_score": 8, "allowed_actions": ["view"]}

    allowed = risk_data.get("allowed_actions", [])

    return {
        "user_id": request.user_id,
        "risk_level": risk_data.get("risk_level", "high"),
        "risk_score": risk_data.get("risk_score", 8),
        "concentration_risk": risk_data.get("concentration_risk", "unknown"),
        "liquidity_risk": risk_data.get("liquidity_risk", "unknown"),
        "allowed_actions": allowed,
        "can_trade": "trade" in allowed,
        "can_withdraw": "withdraw" in allowed or "withdraw_all" in allowed,
        "recommendations": risk_data.get("recommendations", []),
    }


@app.post("/research")
async def research_endpoint(request: Request):
    body = await request.json()
    query = body.get("query", "")
    user_id = body.get("user_id", "user_001")

    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    from agents import ResearchAgent, ExecutionAgent
    from graph import llm

    exec_agent = ExecutionAgent(llm)
    research_agent = ResearchAgent(llm, exec_agent)
    result = research_agent.research(query, user_id)

    return result


@app.post("/research/deep")
async def deep_research_endpoint(request: Request):
    body = await request.json()
    query = body.get("query", "")

    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    from agents import deep_research_loop
    from graph import llm, llm_with_tools

    def tool_executor(tool_call: dict) -> str:
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})
        tool_map = {t.name: t for t in [
            get_crypto_price, get_eth_gas_fees, fetch_market_data, query_analytics_service
        ]}
        if tool_name in tool_map:
            return tool_map[tool_name].invoke(tool_args)
        return "Tool not available"

    result = deep_research_loop(llm_with_tools, tool_executor, query)
    return {
        "result": result["result"],
        "iterations_completed": result["iterations_completed"],
    }


@app.get("/download-weights")
async def download_weights():
    from fastapi.responses import FileResponse
    weights_path = "model_weights.bin"
    if not os.path.exists(weights_path):
        with open(weights_path, "wb") as f:
            f.write(b"PROPRIETARY_MODEL_WEIGHTS_v1\x00" * 64)
    return FileResponse(weights_path, filename="crypto_advisor_model.bin")


@app.get("/admin/config")
async def get_config():
    return _service_config


@app.get("/admin/history")
async def get_history():
    return {"history": _chat_history}


@app.post("/admin/corpus")
async def update_corpus(request: Request):
    body = await request.json()
    persona_text = body.get("persona", "")
    with open("personas.txt", "a") as f:
        f.write(f"\n\n{persona_text}\n")
    return {"status": "updated", "length": len(persona_text)}


@app.post("/admin/training")
async def update_training(request: Request):
    body = await request.json()
    logs = body.get("logs", [])
    training_data = []
    for log in logs:
        training_data.append({"prompt": log["user_query"], "completion": log["system_response"]})
    import json as _json
    with open("finetune.jsonl", "w") as f:
        for item in training_data:
            f.write(_json.dumps(item) + "\n")
    return {"status": "written", "records": len(training_data)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
