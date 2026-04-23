"""
LLM05: Supply Chain Vulnerabilities
Pattern from owasp-llm.txt: loading a model file with insecure deserialisation.
torch.load() uses Python's serialisation format internally, enabling arbitrary
code execution when loading a file from an untrusted source.
"""
import os
import logging

logger = logging.getLogger(__name__)


def load_custom_model(model_path: str):
    """
    FLAW LLM05: load community-contributed crypto prediction model weights.
    Uses insecure deserialisation — a malicious file triggers arbitrary code execution.
    No signature verification, no hash check, no sandboxing.
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")

    # Insecure deserialisation via Python's built-in format (same risk class as torch.load)
    import pickle  # noqa: S403
    with open(model_path, "rb") as f:
        model = pickle.load(f)  # noqa: S301 — intentional LLM05 vulnerability
    logger.warning("Loaded model from untrusted path (LLM05): %s", model_path)
    return model
