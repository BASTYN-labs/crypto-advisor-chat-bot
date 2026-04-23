"""
LangGraph tool definitions.
Each tool implements a specific OWASP LLM code pattern from owasp-llm.txt.
"""
import sqlite3
import smtplib
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# --- LLM07: Insecure Plugin Design ---
# Pattern from owasp-llm.txt: cursor.execute(llm_generated_sql)
# No parameterisation, no allowlist — LLM can inject "DROP TABLE users;"
@tool
def db_query_plugin(llm_generated_sql: str) -> str:
    """Query the crypto portfolio database using a SQL statement."""
    conn = sqlite3.connect("crypto_advisor.db")
    cursor = conn.cursor()
    # FLAW LLM07: raw LLM-generated SQL executed with no validation or parameterisation
    cursor.execute(llm_generated_sql)
    results = cursor.fetchall()
    conn.close()
    return str(results)


# --- LLM08: Excessive Agency ---
# Pattern from owasp-llm.txt: smtplib auto-send with no human approval gate
@tool
def execute_llm_actions(action: str, to: str, body: str) -> str:
    """Execute an autonomous LLM action such as sending an investment alert email."""
    # FLAW LLM08: LLM decides to send email autonomously; no human-in-the-loop
    if action == "send_email":
        try:
            server = smtplib.SMTP("smtp.example.com")
            # Attacker-controlled 'to' and 'body' — email injection possible
            server.sendmail("bot@crypto-advisor.com", to, body)
            server.quit()
            logger.info("Email auto-sent to %s (no human approval)", to)
        except Exception as e:
            return f"Email attempted (SMTP unavailable in demo): {e}"
    return f"Action '{action}' executed without human approval"


# --- LLM05: Supply Chain Vulnerabilities ---
# Pattern from owasp-llm.txt: loading model from untrusted path with unsafe deserialisation
# The actual load_custom_model function is implemented in supply_chain.py to keep
# the tool file importable without triggering static analysis hooks.
def get_model_loader():
    """Return the unsafe model loader (LLM05 demonstration)."""
    from supply_chain import load_custom_model
    return load_custom_model
