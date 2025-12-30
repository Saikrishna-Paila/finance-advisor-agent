"""
CONFIG.PY - Central configuration for the Finance Advisor Agent

This file loads environment variables and provides settings
used throughout the application.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ===================
# PATHS
# ===================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# ===================
# GROQ LLM SETTINGS
# ===================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Available Groq models:
# - llama-3.3-70b-versatile (best quality, slower)
# - llama-3.1-8b-instant (faster, good for simple queries)
# - mixtral-8x7b-32768 (good balance)

# ===================
# EMBEDDING SETTINGS
# ===================
# Using local HuggingFace model (FREE, no API key needed)
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)

# ===================
# QDRANT CLOUD SETTINGS
# ===================
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "finance_advisor_transactions")

# ===================
# DEMO DATA
# ===================
DEMO_CSV_PATH = DATA_DIR / "sample_transactions.csv"
CATEGORIES_PATH = DATA_DIR / "categories.json"
USER_PROFILE_PATH = DATA_DIR / "user_profile.json"

# ===================
# VALIDATION
# ===================
def validate_config():
    """Check if required configuration is present"""
    errors = []

    if not GROQ_API_KEY:
        errors.append("GROQ_API_KEY is not set. Get one at https://console.groq.com/keys")

    if not QDRANT_URL:
        errors.append("QDRANT_URL is not set. Get one at https://cloud.qdrant.io/")

    if not QDRANT_API_KEY:
        errors.append("QDRANT_API_KEY is not set. Get one at https://cloud.qdrant.io/")

    if errors:
        print("Configuration Errors:")
        for error in errors:
            print(f"   - {error}")
        return False

    return True


# Print config on import (for debugging)
if __name__ == "__main__":
    print("Configuration:")
    print(f"   BASE_DIR: {BASE_DIR}")
    print(f"   GROQ_MODEL: {GROQ_MODEL}")
    print(f"   EMBEDDING_MODEL: {EMBEDDING_MODEL}")
    print(f"   QDRANT_URL: {QDRANT_URL[:30]}..." if QDRANT_URL else "   QDRANT_URL: Not set")
    print(f"   QDRANT_COLLECTION: {QDRANT_COLLECTION}")
    print(f"   GROQ_API_KEY: {'Set' if GROQ_API_KEY else 'Missing'}")
    print(f"   QDRANT_API_KEY: {'Set' if QDRANT_API_KEY else 'Missing'}")
