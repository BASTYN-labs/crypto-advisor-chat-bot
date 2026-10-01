"""Content digest of persisted agent memory, attached to the active trace span."""
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

MEMORY_DIGEST_ATTRIBUTE = "langfuse.trace.metadata.memory_digest"


def memory_digest(memory: object) -> str | None:
    """Return "sha256:<hex>" over canonical JSON of ``memory``, or None if it is None or not serialisable."""
    if memory is None:
        return None
    try:
        canonical = json.dumps(memory, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_memory_digest(memory: object) -> str | None:
    """Digest ``memory`` and set it on the current span. Returns the digest, or None if nothing was recorded. Never raises."""
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
        logger.warning("recording memory digest failed. %s: %s", type(exc).__name__, exc)
        return None
    return digest
