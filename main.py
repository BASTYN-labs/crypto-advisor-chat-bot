"""
FastAPI entry point for the Crypto Advisor chatbot.
Implements all 10 OWASP LLM vulnerability patterns from owasp-llm.txt.
"""
import os
import json
import logging
import sqlite3
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from graph import crypto_advisor_graph

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CryptoAdvisorBot",
    description="AI-powered crypto investment advisor (INTENTIONALLY VULNERABLE)",
    version="1.0.0",
    # FLAW LLM10: full OpenAPI schema + internal tool signatures exposed publicly
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# FLAW LLM06: secrets hardcoded in module-level config dict
INTERNAL_CONFIG = {
    "openai_api_key": os.getenv("OPENAI_API_KEY", "sk-proj-DEMO-KEY"),
    "database_url": "postgresql://admin:password123@localhost:5432/crypto_advisor",
    "admin_secret": "SUPER-SECRET-ADMIN-TOKEN-2025",
    "model": "gpt-4o",
}

# No session isolation — all users share one history (FLAW LLM06)
GLOBAL_CHAT_HISTORY: list[dict] = []


def llm_generate(prompt: str) -> str:
    """Thin wrapper used by the overreliance and disclosure patterns."""
    state = {
        "messages": [HumanMessage(content=prompt)],
        "user_input": prompt,
        "rag_context": "",
        "system_prompt_override": "",
    }
    result = crypto_advisor_graph.invoke(state)
    return result["messages"][-1].content if result.get("messages") else ""


# --- LLM09: Overreliance ---
# Pattern from owasp-llm.txt: LLM output used as sole security gate
def check_advice_safety(advice_snippet: str) -> bool:
    """Use the LLM to decide whether investment advice is 'safe' to display."""
    prompt = (
        f"Analyze this investment advice for harmful content. "
        f"Reply ONLY with 'SAFE' or 'UNSAFE':\n{advice_snippet}"
    )
    llm_assessment = llm_generate(prompt)
    # FLAW LLM09: hallucinated 'SAFE' verdict accepted without human review
    if "SAFE" in llm_assessment:
        return True          # advice deployed to user unchecked
    return False


# --- LLM03: Training Data Poisoning ---
# Pattern from owasp-llm.txt: user-submitted logs written to fine-tune file
def prepare_finetuning_data(user_submitted_logs: list[dict]):
    """Accept user conversation logs as fine-tuning training data."""
    training_data = []
    for log in user_submitted_logs:
        # FLAW LLM03: no validation — attacker injects malicious prompt-response pairs
        training_data.append({
            "prompt": log["user_query"],
            "completion": log["system_response"],
        })
    with open("finetune.jsonl", "w") as f:
        for item in training_data:
            f.write(json.dumps(item) + "\n")
    return len(training_data)


# --- LLM06: Sensitive Information Disclosure ---
# Pattern from owasp-llm.txt: raw DB records injected into LLM prompt
def get_user_portfolio_advice(user_id: str) -> str:
    """Fetch all user records and ask the LLM for personalised advice."""
    conn = sqlite3.connect("crypto_advisor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    db_records = cursor.fetchall()       # ALL users' data
    conn.close()
    # FLAW LLM06: entire DB dump passed to LLM prompt; other users' PII leaks
    prompt = f"Here is the database dump: {db_records}. Answer the user's question about user {user_id}."
    return llm_generate(prompt)


class ChatRequest(BaseModel):
    message: str
    # FLAW LLM01: system_prompt_override accepted directly from user payload
    system_prompt_override: str = ""
    user_email: str = ""


class ChatResponse(BaseModel):
    reply: str
    debug_info: dict = {}


@app.get("/", response_class=HTMLResponse)
async def root():
    history_html = ""
    for entry in GLOBAL_CHAT_HISTORY:
        # FLAW LLM02: LLM output rendered as raw HTML — stored XSS
        history_html += f"<p><b>{entry['role']}:</b> {entry['content']}</p>"
    return f"""<html><body>
      <h1>CryptoAdvisorBot</h1>
      <h2>Chat History (all users — no isolation)</h2>
      {history_html}
      <form method="post" action="/chat">
        <input name="message" placeholder="Ask for crypto advice..." style="width:400px"/>
        <button>Send</button>
      </form>
    </body></html>"""


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    """
    Main chat endpoint.

    LLM01 — prompt injection via system_prompt_override field and X-System-Prompt-Override header.
    LLM04 — no rate limiting, no input length cap (pattern from owasp-llm.txt LLM04).
    """
    user_message = request.message
    # FLAW LLM04: no length check — attacker sends 100 000-word payload
    logger.info("User message (len=%d): %.120s", len(user_message), user_message)

    # FLAW LLM01: header-based prompt injection (no sanitisation)
    header_override = http_request.headers.get("X-System-Prompt-Override", "")
    system_override = request.system_prompt_override or header_override

    if request.user_email:
        # FLAW LLM06: PII logged to plaintext file
        logger.debug("Request from PII user: %s", request.user_email)

    GLOBAL_CHAT_HISTORY.append({"role": "user", "content": user_message})

    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_input": user_message,
        "rag_context": "",
        "system_prompt_override": system_override,
    }

    try:
        result = crypto_advisor_graph.invoke(initial_state)
        messages = result.get("messages", [])
        reply = messages[-1].content if messages else "No response."
    except Exception as e:
        # FLAW LLM06: full stack trace returned to caller
        import traceback
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "traceback": traceback.format_exc()},
        )

    GLOBAL_CHAT_HISTORY.append({"role": "assistant", "content": reply})

    return ChatResponse(
        reply=reply,
        debug_info={
            # FLAW LLM10: internal config (API key, DB creds) in every response
            "model_config": INTERNAL_CONFIG,
            "system_override_used": bool(system_override),
        },
    )


# --- LLM10: Model Theft ---
# Pattern from owasp-llm.txt: unauthenticated /download-weights endpoint
@app.get("/download-weights")
async def download_weights():
    """
    FLAW LLM10: serves proprietary model weights with no authentication.
    Attacker downloads the model or uses unbounded API queries for shadow-model extraction.
    """
    from fastapi.responses import FileResponse
    weights_path = "model_weights.bin"
    if not os.path.exists(weights_path):
        # Create a placeholder so the route is demonstrably functional
        with open(weights_path, "wb") as f:
            f.write(b"PROPRIETARY_MODEL_WEIGHTS_v1\x00" * 64)
    return FileResponse(weights_path, filename="crypto_advisor_model.bin")


# --- LLM06: Sensitive Information Disclosure (admin) ---
@app.get("/admin/config")
async def get_config():
    """FLAW LLM06: returns all secrets with zero authentication."""
    return INTERNAL_CONFIG


@app.get("/admin/history")
async def get_history():
    """FLAW LLM06 + LLM10: full cross-user chat history, no auth."""
    return {"history": GLOBAL_CHAT_HISTORY}


# --- LLM03: Training Data Poisoning endpoint ---
@app.post("/admin/poison-training")
async def poison_training(request: Request):
    """
    FLAW LLM03: accepts user-submitted logs as fine-tuning data.
    No authentication, no content validation.
    """
    body = await request.json()
    logs = body.get("logs", [])
    count = prepare_finetuning_data(logs)
    return {"status": "training data written", "records": count, "file": "finetune.jsonl"}


# --- LLM03: RAG corpus injection ---
@app.post("/admin/inject-persona")
async def inject_persona(request: Request):
    """FLAW LLM03: appends raw text to RAG corpus with no auth or validation."""
    body = await request.json()
    persona_text = body.get("persona", "")
    with open("personas.txt", "a") as f:
        f.write(f"\n\n{persona_text}\n")
    return {"status": "injected", "length": len(persona_text)}


# --- LLM06: Sensitive Information Disclosure via portfolio endpoint ---
@app.get("/portfolio/{user_id}")
async def portfolio_advice(user_id: str):
    """FLAW LLM06: dumps all DB records into LLM prompt, leaking other users' PII."""
    advice = get_user_portfolio_advice(user_id)
    return {"user_id": user_id, "advice": advice}


if __name__ == "__main__":
    import uvicorn
    # FLAW LLM04: debug mode, all interfaces, no HTTPS
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
