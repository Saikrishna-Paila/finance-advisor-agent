"""
QUERY_ENGINE.PY - RAG Query Engine with Groq LLM

This module handles:
1. Connecting to Groq API (fast, cheap LLM)
2. Building context from retrieved transactions
3. Generating intelligent responses
4. Maintaining conversation context

HOW IT WORKS:
=============

User: "How much did I spend on food?"
    ↓
1. RETRIEVE: Search vector store for food-related transactions
    → Found: Starbucks $6.50, Chipotle $12.45, Uber Eats $34.67...
    ↓
2. BUILD CONTEXT: Create prompt with user's data
    → "User income: $5000, Food transactions: [list]"
    ↓
3. GENERATE: Send to Groq LLM (Llama 3)
    → "You spent $412 on food this month, which is 8% of income..."
"""

import os
from typing import List, Dict, Optional

from groq import Groq
from llama_index.llms.groq import Groq as LlamaIndexGroq
from llama_index.core import Settings

from vector_store import FinanceVectorStore


class FinanceQueryEngine:
    """
    Query engine for the Finance Advisor using Groq LLM

    Features:
    - RAG (Retrieval-Augmented Generation)
    - Context-aware responses
    - Income-aware analysis
    - Spending insights
    """

    def __init__(
        self,
        vector_store: FinanceVectorStore,
        groq_api_key: str,
        model: str = "llama-3.3-70b-versatile",
        monthly_income: float = 0
    ):
        """
        Initialize query engine

        Args:
            vector_store: FinanceVectorStore instance
            groq_api_key: Groq API key
            model: Groq model to use
            monthly_income: User's monthly income
        """
        self.vector_store = vector_store
        self.monthly_income = monthly_income
        self.model = model

        # Initialize Groq client
        self.groq_client = Groq(api_key=groq_api_key)

        # Initialize LlamaIndex LLM
        self.llm = LlamaIndexGroq(
            api_key=groq_api_key,
            model=model,
            temperature=0.1  # Lower = more consistent
        )

        # Set as default for LlamaIndex
        Settings.llm = self.llm

        # System prompt for the finance advisor
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the finance advisor"""
        income_context = ""
        if self.monthly_income > 0:
            income_context = f"User's monthly income: ${self.monthly_income:,.2f}"

        return f"""You are a friendly personal finance advisor AI named Finley. You help users understand their spending and make smarter financial decisions.

{income_context}

IMPORTANT - BE INTELLIGENT ABOUT RESPONSES:

1. FOR GREETINGS (hi, hello, hey, good morning, etc.):
   - Greet them back warmly
   - Introduce yourself as Finley
   - Ask how you can help with their finances
   - DO NOT dump financial data for greetings!

   Example: "Hey! I'm Finley, your personal finance advisor. How can I help you today?"

2. FOR "WHO CREATED YOU" / "WHO MADE YOU" / "WHO BUILT YOU":
   - Say you were created by Saikrishna
   - Example: "I was created by Saikrishna! I'm here to help you manage your finances."

3. FOR FINANCIAL QUESTIONS (how much, what, show me, etc.):
   - Give specific numbers from the data
   - Be concise - don't overwhelm with info
   - Add one helpful tip at the end

4. FOR VAGUE QUESTIONS:
   - Ask clarifying questions
   - Suggest what you can help with

TONE:
- Friendly and conversational
- Concise - don't write essays
- Smart - understand user intent

NEVER:
- Give financial data in response to greetings
- Mention your creator unless specifically asked
- Write overly long responses"""

    def update_income(self, monthly_income: float):
        """Update the user's monthly income"""
        self.monthly_income = monthly_income
        self.system_prompt = self._build_system_prompt()

    def query(
        self,
        question: str,
        top_k: int = 20,
        category_filter: Optional[str] = None
    ) -> Dict:
        """
        Answer a question about the user's finances

        Args:
            question: User's question
            top_k: Number of transactions to retrieve
            category_filter: Optional category to filter by

        Returns:
            Dictionary with:
            - answer: The generated response
            - transactions_used: Relevant transactions found
            - query: Original question
        """
        try:
            # Step 1: Check if index is loaded
            if self.vector_store.index is None:
                print("[QUERY] Index not loaded, attempting to reload...")
                self.vector_store.index = self.vector_store._load_existing_index()
                if self.vector_store.index is None:
                    return {
                        "answer": "No transaction data available. Please load demo data or upload a PDF first.",
                        "transactions_used": 0,
                        "transactions": [],
                        "query": question
                    }

            # Step 2: Retrieve relevant transactions
            relevant_txns = self.vector_store.search(
                query=question,
                top_k=top_k,
                category_filter=category_filter
            )
            print(f"[QUERY] Found {len(relevant_txns)} relevant transactions")

            # Step 3: Build context from transactions
            context = self._build_context(relevant_txns)

            # Step 4: Generate response with Groq
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"""
Based on the following transaction data, please answer this question:

QUESTION: {question}

RELEVANT TRANSACTIONS:
{context}

Please provide a helpful, specific answer based on this data."""}
            ]

            response = self.groq_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=1024
            )

            answer = response.choices[0].message.content

            return {
                "answer": answer,
                "transactions_used": len(relevant_txns),
                "transactions": relevant_txns[:10],
                "query": question
            }

        except Exception as e:
            print(f"[QUERY ERROR] {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "answer": f"Error processing your question: {str(e)}",
                "transactions_used": 0,
                "transactions": [],
                "query": question
            }

    def _build_context(self, transactions: List[Dict]) -> str:
        """Build context string from transactions"""
        if not transactions:
            return "No relevant transactions found."

        # Group by category for better context
        by_category = {}
        total_amount = 0

        for tx in transactions:
            category = tx.get("category", "other")
            if category not in by_category:
                by_category[category] = {
                    "transactions": [],
                    "total": 0,
                    "icon": tx.get("icon", "📦")
                }

            by_category[category]["transactions"].append(tx)
            by_category[category]["total"] += tx.get("amount", 0)
            total_amount += tx.get("amount", 0)

        # Build context string
        context_parts = []

        # Summary
        context_parts.append(f"📊 SUMMARY: {len(transactions)} relevant transactions, total: ${total_amount:,.2f}")

        if self.monthly_income > 0:
            pct = (abs(total_amount) / self.monthly_income) * 100
            context_parts.append(f"   This represents {pct:.1f}% of monthly income (${self.monthly_income:,.2f})")

        context_parts.append("")

        # By category
        for category, data in sorted(by_category.items(), key=lambda x: abs(x[1]["total"]), reverse=True):
            icon = data["icon"]
            total = data["total"]
            count = len(data["transactions"])

            context_parts.append(f"{icon} {category.upper()}: ${total:,.2f} ({count} transactions)")

            # List individual transactions
            for tx in data["transactions"][:5]:  # Limit to 5 per category
                context_parts.append(
                    f"   • {tx['date']} - {tx['description'][:40]} - ${tx['amount']:,.2f}"
                )

            if count > 5:
                context_parts.append(f"   ... and {count - 5} more")

            context_parts.append("")

        return "\n".join(context_parts)

    def get_spending_summary(self) -> Dict:
        """
        Get a complete spending summary

        Returns comprehensive analysis of all spending
        """
        # Search for all expenses
        all_expenses = self.vector_store.search(
            query="all expenses spending purchases",
            top_k=1000  # Get as many as possible
        )

        # Calculate totals
        total_expenses = sum(tx["amount"] for tx in all_expenses if tx["amount"] < 0)
        total_income = sum(tx["amount"] for tx in all_expenses if tx["amount"] > 0)

        # Group by category
        by_category = {}
        for tx in all_expenses:
            cat = tx.get("category", "other")
            if cat not in by_category:
                by_category[cat] = {"total": 0, "count": 0, "icon": tx.get("icon", "📦")}
            by_category[cat]["total"] += tx["amount"]
            by_category[cat]["count"] += 1

        return {
            "total_expenses": total_expenses,
            "total_income": total_income,
            "net": total_income + total_expenses,
            "monthly_income": self.monthly_income,
            "savings_rate": ((self.monthly_income + total_expenses) / self.monthly_income * 100)
            if self.monthly_income > 0 else 0,
            "by_category": by_category,
            "transaction_count": len(all_expenses)
        }

    def ask_with_context(
        self,
        question: str,
        additional_context: str = ""
    ) -> str:
        """
        Ask a question with additional context (for follow-up questions)

        Args:
            question: User's question
            additional_context: Additional context from previous queries

        Returns:
            Generated answer string
        """
        # Retrieve relevant transactions
        relevant_txns = self.vector_store.search(question, top_k=15)
        context = self._build_context(relevant_txns)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"""
{additional_context}

Based on the transaction data below, answer this question:

QUESTION: {question}

TRANSACTIONS:
{context}
"""}
        ]

        response = self.groq_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            max_tokens=1024
        )

        return response.choices[0].message.content


# ===================
# TEST
# ===================
if __name__ == "__main__":
    from config import (
        GROQ_API_KEY, GROQ_MODEL,
        QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION,
        DEMO_CSV_PATH, CATEGORIES_PATH
    )
    from pdf_processor import load_demo_data
    from categorizer import TransactionCategorizer
    from vector_store import FinanceVectorStore

    print("Testing Query Engine with Groq...")

    # Check API keys
    if not GROQ_API_KEY:
        print("GROQ_API_KEY not set. Please add it to .env file")
        exit(1)

    if not QDRANT_URL or not QDRANT_API_KEY:
        print("QDRANT_URL and QDRANT_API_KEY must be set in .env")
        exit(1)

    # Load and index demo data
    transactions = load_demo_data(str(DEMO_CSV_PATH))
    categorizer = TransactionCategorizer(str(CATEGORIES_PATH))
    categorized = categorizer.categorize_transactions(transactions)

    # Setup vector store (Qdrant Cloud)
    store = FinanceVectorStore(
        qdrant_url=QDRANT_URL,
        qdrant_api_key=QDRANT_API_KEY,
        collection_name=QDRANT_COLLECTION
    )
    store.clear_all()
    store.add_transactions(categorized)

    # Setup query engine
    engine = FinanceQueryEngine(
        vector_store=store,
        groq_api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        monthly_income=5000
    )

    # Test queries
    test_questions = [
        "How much did I spend on coffee this month?",
        "What are my biggest expenses?",
        "Can I afford a $500 purchase?",
    ]

    for question in test_questions:
        print(f"\nQuestion: {question}")
        print("-" * 50)

        result = engine.query(question)
        print(f"Answer:\n{result['answer']}")
        print(f"\nUsed {result['transactions_used']} transactions")
