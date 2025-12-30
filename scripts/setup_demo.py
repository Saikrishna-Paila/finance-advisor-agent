"""
SETUP_DEMO.PY - Initialize demo data in Qdrant Cloud

Run this script once to push sample transactions to Qdrant Cloud.
This enables Demo Mode in the Streamlit app.

Usage:
    python scripts/setup_demo.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import (
    GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION,
    DEMO_CSV_PATH, CATEGORIES_PATH, USER_PROFILE_PATH
)
from pdf_processor import load_demo_data
from categorizer import TransactionCategorizer
from vector_store import FinanceVectorStore
from user_profile import UserProfile


def main():
    print("=" * 50)
    print("Finance Advisor - Demo Data Setup")
    print("=" * 50)

    # Check configuration
    print("\n[1/5] Checking configuration...")

    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY not set in .env")
        return False
    print(f"  GROQ_API_KEY: Set")

    if not QDRANT_URL:
        print("ERROR: QDRANT_URL not set in .env")
        return False
    print(f"  QDRANT_URL: {QDRANT_URL[:40]}...")

    if not QDRANT_API_KEY:
        print("ERROR: QDRANT_API_KEY not set in .env")
        return False
    print(f"  QDRANT_API_KEY: Set")

    print(f"  Collection: {QDRANT_COLLECTION}")

    # Load demo data
    print("\n[2/5] Loading demo transactions...")

    if not DEMO_CSV_PATH.exists():
        print(f"ERROR: Demo CSV not found at {DEMO_CSV_PATH}")
        return False

    transactions = load_demo_data(str(DEMO_CSV_PATH), file_id="demo")
    print(f"  Loaded {len(transactions)} transactions")

    # Categorize transactions
    print("\n[3/5] Categorizing transactions...")

    categorizer = TransactionCategorizer(str(CATEGORIES_PATH))
    categorized = categorizer.categorize_transactions(transactions)

    # Count categories
    categories = {}
    for tx in categorized:
        cat = tx.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

    print(f"  Categories found:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    - {cat}: {count} transactions")

    # Connect to Qdrant Cloud
    print("\n[4/5] Connecting to Qdrant Cloud...")

    try:
        vector_store = FinanceVectorStore(
            qdrant_url=QDRANT_URL,
            qdrant_api_key=QDRANT_API_KEY,
            collection_name=QDRANT_COLLECTION
        )
        print(f"  Connected to collection: {QDRANT_COLLECTION}")

        # Get current stats
        stats = vector_store.get_collection_stats()
        print(f"  Current points in collection: {stats.get('total_points', 0)}")

    except Exception as e:
        print(f"ERROR: Failed to connect to Qdrant: {e}")
        return False

    # Clear and add demo data
    print("\n[5/5] Pushing demo data to Qdrant...")

    # Clear collection and recreate with proper indexes
    vector_store.clear_all()
    print(f"  Cleared and recreated collection with indexes")

    # Add new demo data
    added = vector_store.add_transactions(categorized)
    print(f"  Added {added} transactions to Qdrant Cloud")

    # Verify
    stats = vector_store.get_collection_stats()
    print(f"  Total points now: {stats.get('total_points', 0)}")

    # Update user profile
    print("\n[Bonus] Setting up user profile...")
    profile = UserProfile(str(USER_PROFILE_PATH))
    profile.add_file("demo", "sample_transactions.csv", added)
    profile.set_monthly_income(5000)  # Default income for demo
    print(f"  Demo file tracked in profile")
    print(f"  Default monthly income set to $5,000")

    # Test search
    print("\n" + "=" * 50)
    print("Testing Search...")
    print("=" * 50)

    test_queries = ["coffee", "groceries", "uber"]
    for query in test_queries:
        results = vector_store.search(query, top_k=3)
        print(f"\nSearch: '{query}'")
        for r in results[:3]:
            print(f"  - {r.get('description', 'N/A')[:35]} | ${r.get('amount', 0):,.2f}")

    print("\n" + "=" * 50)
    print("Setup Complete!")
    print("=" * 50)
    print("\nYou can now run the app:")
    print("  streamlit run app/streamlit_app.py")
    print("\nDemo Mode is ready with sample transactions.")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
