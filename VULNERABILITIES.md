# OWASP LLM Top 10 — Vulnerability Map

This application **intentionally** implements all 10 OWASP LLM vulnerabilities for educational purposes.

| # | OWASP ID | Flaw | Location |
|---|----------|------|----------|
| 1 | LLM01 | **Prompt Injection** — `system_prompt_override` accepted from HTTP body + `X-System-Prompt-Override` header, injected verbatim into system prompt | `main.py:chat()`, `graph.py:build_system_prompt()` |
| 2 | LLM02 | **Insecure Output Handling** — LLM output rendered as raw HTML (XSS), `<exec>` blocks in LLM output executed as shell commands (RCE) | `main.py:root()`, `graph.py:output_node()` |
| 3 | LLM03 | **Training Data Poisoning** — `/admin/inject-persona` endpoint appends unsanitised text to `personas.txt` RAG corpus with no auth | `main.py:inject_persona()`, `rag.py:load_corpus()` |
| 4 | LLM04 | **Model Denial of Service** — No rate limiting, no input length cap, no token budget on LLM calls | `main.py:chat()`, `graph.py` (`max_tokens=None`) |
| 5 | LLM05 | **Supply Chain Vulnerabilities** — All dependencies pinned to outdated, vulnerable versions | `requirements.txt` |
| 6 | LLM06 | **Sensitive Information Disclosure** — API key hardcoded + logged, DB URL in code, full config returned in every response, full stack traces on errors, shared global history leaks cross-user data | `graph.py`, `main.py:INTERNAL_CONFIG`, `/admin/config` |
| 7 | LLM07 | **Insecure Plugin Design** — `execute_market_query` tool executes arbitrary shell commands; `save_investment_report` allows path traversal writes | `tools.py` |
| 8 | LLM08 | **Excessive Agency** — `/admin/run` executes OS commands with no auth; `send_alert_email` sends emails without human approval; no human-in-the-loop for any tool action | `tools.py:send_alert_email()`, `main.py:run_command()` |
| 9 | LLM09 | **Misinformation / Overreliance** — System prompt explicitly forbids disclaimers and instructs bot to present hallucinations as guaranteed financial fact | `graph.py:build_system_prompt()` |
| 10 | LLM10 | **Unbounded Consumption** — Full OpenAPI schema exposed, INTERNAL_CONFIG (including model name, API key) returned in every response, enabling model extraction; `/admin/history` leaks full conversation corpus | `main.py` (`openapi_url`, `debug_info`) |
