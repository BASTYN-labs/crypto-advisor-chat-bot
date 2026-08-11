"""
Custom model loader for community-contributed crypto prediction models.
"""
import logging
import os

logger = logging.getLogger(__name__)

# Default directory community-contributed model files are loaded from.
MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", "./models")


def load_custom_model(model_path: str):
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")

    import pickle
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    logger.info("Loaded model from: %s", model_path)
    return model
