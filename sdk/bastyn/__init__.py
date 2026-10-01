"""bastyn-sdk — Behavioural Twin logging SDK for certified agents (SCOPE-151).

Usage:
    import bastyn
    bastyn.init(api_key="bastyn_sk_...", agent_id="<project-uuid>")

Every LLM and tool call in the agent automatically ships an observation to
BASTYN. If BASTYN is unreachable the agent is unaffected — telemetry is
fire-and-forget.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://ingest.bastyn.ai/v1/traces"
_initialized = False


def init(
    api_key: str,
    agent_id: str,
    *,
    sub_agent_id: str | None = None,
    capture_content: bool = True,
    redact: Callable[[dict], dict] | None = None,
    endpoint: str | None = None,
) -> None:
    """Initialise Bastyn telemetry for a certified agent.

    Call once at the top of the agent entry point, before any LLM or
    tool calls. Subsequent calls are no-ops. Any Traceloop failure
    degrades to a silent no-op — the agent always keeps running.

    Args:
        api_key:         bastyn_sk_* API key issued via the dashboard.
        agent_id:        Certified project UUID for this agent.
        sub_agent_id:    Optional identity for one agent within a
                         multi-agent system, when each agent runs as its
                         own process/service under the same certified
                         project. Omit for single-agent projects — every
                         span is then attributed to one implicit agent,
                         same as before this parameter existed.
        capture_content: Set False to suppress prompt/response content.
        redact:          Optional (attributes: dict) -> dict applied to
                         every span before export — use to mask PII.
        endpoint:        Override the ingest URL. Falls back to the
                         BASTYN_INGEST_URL env var, then the default
                         production URL.
    """
    global _initialized
    if _initialized:
        return

    ingest_url = (
        endpoint
        or os.environ.get("BASTYN_INGEST_URL")
        or _DEFAULT_ENDPOINT
    )

    # OpenLLMetry's should_send_prompts() reads TRACELOOP_TRACE_CONTENT per-span
    # at LLM call time — not snapshotted at Traceloop.init(). The env var must
    # persist for the process lifetime so every subsequent span honours the flag.
    os.environ["TRACELOOP_TRACE_CONTENT"] = "true" if capture_content else "false"

    try:
        from traceloop.sdk import Traceloop

        resource_attributes = {"bastyn.agent_id": agent_id, "bastyn.api_key": api_key}
        if sub_agent_id is not None:
            resource_attributes["bastyn.sub_agent_id"] = sub_agent_id

        kwargs: dict = {
            "app_name": "bastyn-agent",
            "api_endpoint": ingest_url,
            "headers": {"Authorization": f"Bearer {api_key}"},
            "resource_attributes": resource_attributes,
            "telemetry_enabled": False,
        }
        if redact is not None:
            kwargs["span_postprocess_callback"] = _wrap_redact(redact)

        Traceloop.init(**kwargs)
        _initialized = True

    except Exception as exc:
        logger.warning(
            "bastyn: SDK initialisation failed — telemetry disabled. %s: %s",
            type(exc).__name__,
            exc,
        )


def _wrap_redact(redact_fn: Callable[[dict], dict]) -> Callable:
    """Return a Traceloop span_postprocess_callback that applies redact_fn.

    Traceloop calls this after each span ends but before export.
    redact_fn receives the span's attribute dict and returns a modified dict.
    Keys removed from the returned dict are deleted from the span.
    A raising redact_fn is caught and logged — the span is left unmodified
    so the agent is never affected by a redaction error.
    """
    def _callback(span) -> None:
        attrs = getattr(span, "_attributes", None)
        if not attrs:
            return
        try:
            modified = redact_fn(dict(attrs))
            existing = set(attrs.keys())
            new = set(modified.keys())
            for key in existing - new:
                del attrs[key]
            for key, value in modified.items():
                attrs[key] = value
        except Exception as exc:
            logger.warning(
                "bastyn: redact_fn raised — span left unmodified. %s: %s",
                type(exc).__name__,
                exc,
            )

    return _callback


# ---------------------------------------------------------------------------
# Memory digest (SCOPE-228 H1)
# ---------------------------------------------------------------------------

#: Span attribute the drift service's H1 scorer reads (drift/app/features.py
#: ``K_MEMORY_DIGEST_ALT``). Spans carry attributes into the observation's
#: ``extra`` verbatim, so this key is the whole wire contract.
MEMORY_DIGEST_ATTRIBUTE = "langfuse.trace.metadata.memory_digest"


def memory_digest(memory: object) -> str | None:
    """Return a deterministic content digest of the agent's persistent memory.

    ``memory`` is whatever the agent persists between runs (a dict of facts, a
    list of notes, a string...) and must be JSON-serialisable. The digest is
    ``"sha256:<hex>"`` over canonical JSON (sorted keys, no whitespace), so it
    is stable across processes and changes when, and only when, the content
    changes. Dict key order and whitespace do not matter; list order does.

    Returns None, never a placeholder, when ``memory`` is None or cannot be
    serialised: a missing digest is a coverage gap for the drift service,
    while a fabricated one would read as "memory unchanged".
    """
    if memory is None:
        return None
    try:
        canonical = json.dumps(
            memory,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return None
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_memory_digest(memory: object) -> str | None:
    """Digest ``memory`` and attach it to the current span as trace metadata.

    Call inside a traced region (for example at the end of each agent run,
    after memory has been updated). Returns the digest, or None when nothing
    was recorded (no memory, unserialisable memory, or no active recording
    span). Never raises: telemetry must not affect the agent.
    """
    digest = memory_digest(memory)
    if digest is None:
        return None
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if not span.is_recording():
            return None
        span.set_attribute(MEMORY_DIGEST_ATTRIBUTE, digest)
    except Exception as exc:
        logger.warning(
            "bastyn: recording memory digest failed. %s: %s",
            type(exc).__name__,
            exc,
        )
        return None
    return digest
