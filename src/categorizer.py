"""
CATEGORIZER.PY - Automatically categorize transactions

This module handles:
1. Loading category definitions from JSON
2. Matching transactions to categories based on keywords
3. Adding category metadata to transactions

HOW IT WORKS:
=============
We have a categories.json with keywords for each category:

    "dining": {
        "keywords": ["starbucks", "chipotle", "mcdonald"],
        "icon": "🍽️"
    }

When we see "STARBUCKS #1234", we match it to "dining" category.
"""

import json
from typing import Dict, List, Optional
from pathlib import Path


class TransactionCategorizer:
    """Categorize transactions based on description keywords"""

    def __init__(self, categories_path: str):
        """
        Initialize categorizer with category definitions

        Args:
            categories_path: Path to categories.json file
        """
        self.categories = self._load_categories(categories_path)
        self.keyword_map = self._build_keyword_map()

    def _load_categories(self, path: str) -> Dict:
        """Load categories from JSON file"""
        with open(path, 'r') as f:
            data = json.load(f)
        return data.get("categories", {})

    def _build_keyword_map(self) -> Dict[str, str]:
        """
        Build a reverse map: keyword -> category

        This makes lookup faster when categorizing
        """
        keyword_map = {}

        for category, info in self.categories.items():
            for keyword in info.get("keywords", []):
                keyword_map[keyword.lower()] = category

        return keyword_map

    def categorize(self, description: str) -> Dict:
        """
        Categorize a single transaction based on its description

        Args:
            description: Transaction description (e.g., "STARBUCKS #1234")

        Returns:
            Dictionary with category info:
            {
                "category": "dining",
                "icon": "🍽️",
                "confidence": "keyword_match"
            }
        """
        description_lower = description.lower()

        # Check each keyword
        for keyword, category in self.keyword_map.items():
            if keyword in description_lower:
                return {
                    "category": category,
                    "icon": self.categories[category].get("icon", "📦"),
                    "confidence": "keyword_match"
                }

        # Default to "other" if no match
        return {
            "category": "other",
            "icon": "📦",
            "confidence": "default"
        }

    def categorize_transactions(
        self,
        transactions: List[Dict]
    ) -> List[Dict]:
        """
        Add category info to a list of transactions

        Args:
            transactions: List of transaction dictionaries

        Returns:
            Same list with category, icon, and confidence added
        """
        categorized = []

        for tx in transactions:
            # Get category info
            cat_info = self.categorize(tx.get("description", ""))

            # Add to transaction
            tx_copy = tx.copy()
            tx_copy["category"] = cat_info["category"]
            tx_copy["icon"] = cat_info["icon"]
            tx_copy["category_confidence"] = cat_info["confidence"]

            categorized.append(tx_copy)

        return categorized

    def get_category_summary(
        self,
        transactions: List[Dict]
    ) -> Dict[str, Dict]:
        """
        Get spending summary by category

        Args:
            transactions: List of categorized transactions

        Returns:
            Dictionary with category stats:
            {
                "dining": {
                    "total": -245.50,
                    "count": 15,
                    "icon": "🍽️"
                },
                ...
            }
        """
        summary = {}

        for tx in transactions:
            category = tx.get("category", "other")
            amount = tx.get("amount", 0)

            if category not in summary:
                summary[category] = {
                    "total": 0,
                    "count": 0,
                    "icon": tx.get("icon", "📦"),
                    "transactions": []
                }

            summary[category]["total"] += amount
            summary[category]["count"] += 1
            summary[category]["transactions"].append(tx)

        # Sort by total spending (most spent first)
        sorted_summary = dict(
            sorted(
                summary.items(),
                key=lambda x: abs(x[1]["total"]),
                reverse=True
            )
        )

        return sorted_summary

    def get_all_categories(self) -> List[Dict]:
        """Get list of all available categories"""
        return [
            {
                "name": name,
                "icon": info.get("icon", "📦"),
                "keywords": info.get("keywords", [])
            }
            for name, info in self.categories.items()
        ]


# ===================
# TEST
# ===================
if __name__ == "__main__":
    from config import CATEGORIES_PATH, DEMO_CSV_PATH
    from pdf_processor import load_demo_data

    print("🏷️  Testing Transaction Categorizer...")

    # Load demo data
    transactions = load_demo_data(str(DEMO_CSV_PATH))
    print(f"✓ Loaded {len(transactions)} transactions")

    # Initialize categorizer
    categorizer = TransactionCategorizer(str(CATEGORIES_PATH))
    print(f"✓ Loaded {len(categorizer.categories)} categories")

    # Categorize transactions
    categorized = categorizer.categorize_transactions(transactions)

    # Get summary
    summary = categorizer.get_category_summary(categorized)

    print("\n📊 Spending by Category:")
    print("-" * 50)

    for category, stats in summary.items():
        if stats["total"] < 0:  # Only show expenses
            print(
                f"  {stats['icon']} {category:20} "
                f"${abs(stats['total']):>10.2f} "
                f"({stats['count']} transactions)"
            )
