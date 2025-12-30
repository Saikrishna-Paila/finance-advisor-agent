"""
VECTOR_STORE.PY - Qdrant Cloud + LlamaIndex for RAG

This module handles:
1. Connecting to Qdrant Cloud (API key authentication)
2. Creating embeddings with HuggingFace (free, no API key)
3. Indexing transactions with metadata
4. Searching/retrieving relevant transactions
5. Deleting transactions by file_id
6. Auto-creating collection if it doesn't exist

HOW IT WORKS:
=============

1. EMBED: Convert transaction text to vector (list of numbers)
   "STARBUCKS #1234 -$6.50" → [0.12, -0.45, 0.78, ...]

2. STORE: Save vector + metadata in Qdrant Cloud
   Vector: [0.12, -0.45, 0.78, ...]
   Metadata: {date, category, amount, file_id}

3. SEARCH: Find similar transactions
   Query: "coffee spending"
   → Returns: All Starbucks, Dunkin transactions

4. DELETE: Remove by file_id
   Delete file "abc123" → Removes all its transactions
"""

import os
from typing import List, Dict, Optional
from pathlib import Path

from llama_index.core import (
    VectorStoreIndex,
    Document,
    StorageContext,
    Settings,
)
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType,
)


class FinanceVectorStore:
    """
    Vector store for financial transactions using Qdrant Cloud + LlamaIndex

    Features:
    - Qdrant Cloud storage (shared cluster for all projects)
    - Free embeddings (HuggingFace)
    - Metadata filtering
    - File-based deletion
    - Auto-creates collection if not exists
    """

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str,
        collection_name: str = "finance_advisor_transactions",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        """
        Initialize vector store with Qdrant Cloud

        Args:
            qdrant_url: Qdrant Cloud cluster URL
            qdrant_api_key: Qdrant Cloud API key
            collection_name: Name of the collection
            embedding_model: HuggingFace model for embeddings
        """
        self.qdrant_url = qdrant_url
        self.qdrant_api_key = qdrant_api_key
        self.collection_name = collection_name

        # Initialize Qdrant client (Cloud)
        self.qdrant_client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key
        )

        # Initialize embedding model (local, free)
        self.embed_model = HuggingFaceEmbedding(
            model_name=embedding_model
        )

        # Set as default for LlamaIndex
        Settings.embed_model = self.embed_model

        # Initialize collection if needed (auto-create)
        self._init_collection()

        # Initialize vector store
        self.vector_store = QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=collection_name,
        )

        # Create storage context
        self.storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )

        # Load existing index from Qdrant (if data exists)
        self.index = self._load_existing_index()

    def _load_existing_index(self):
        """Load existing index from Qdrant if data exists"""
        try:
            # Check if collection has data
            info = self.qdrant_client.get_collection(self.collection_name)
            if info.points_count > 0:
                # Create index from existing vector store
                index = VectorStoreIndex.from_vector_store(
                    vector_store=self.vector_store,
                )
                print(f"Loaded {info.points_count} existing points from Qdrant")
                return index
        except Exception as e:
            pass
        return None

    def _init_collection(self):
        """Create collection if it doesn't exist, with payload indexes"""
        collections = self.qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]

        if self.collection_name not in collection_names:
            # Get embedding dimension
            test_embedding = self.embed_model.get_text_embedding("test")
            embedding_dim = len(test_embedding)

            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE
                )
            )
            print(f"Created collection: {self.collection_name}")

            # Create payload indexes for filtering
            self._create_payload_indexes()

    def _create_payload_indexes(self):
        """Create indexes on payload fields for filtering"""
        try:
            # Index for file_id (for deletion)
            self.qdrant_client.create_payload_index(
                collection_name=self.collection_name,
                field_name="file_id",
                field_schema=PayloadSchemaType.KEYWORD
            )
            # Index for category (for filtering)
            self.qdrant_client.create_payload_index(
                collection_name=self.collection_name,
                field_name="category",
                field_schema=PayloadSchemaType.KEYWORD
            )
            print(f"Created payload indexes for filtering")
        except Exception as e:
            # Indexes may already exist
            pass

    def add_transactions(self, transactions: List[Dict]) -> int:
        """
        Add transactions to the vector store

        Args:
            transactions: List of transaction dictionaries with:
                - date
                - description
                - amount
                - category
                - file_id
                - icon

        Returns:
            Number of transactions added
        """
        if not transactions:
            return 0

        # Convert transactions to LlamaIndex nodes
        nodes = []
        for tx in transactions:
            # Create searchable text
            text = self._create_searchable_text(tx)

            # Create node with metadata
            node = TextNode(
                text=text,
                metadata={
                    "date": tx.get("date", ""),
                    "description": tx.get("description", ""),
                    "amount": float(tx.get("amount", 0)),
                    "category": tx.get("category", "other"),
                    "icon": tx.get("icon", "📦"),
                    "type": tx.get("type", "debit"),
                    "file_id": tx.get("file_id", "unknown"),
                },
                excluded_embed_metadata_keys=["icon"],  # Don't embed the icon
                excluded_llm_metadata_keys=["icon"],
            )
            nodes.append(node)

        # Create or update index
        self.index = VectorStoreIndex(
            nodes=nodes,
            storage_context=self.storage_context,
        )

        return len(nodes)

    def _create_searchable_text(self, tx: Dict) -> str:
        """
        Create rich searchable text from transaction

        This text will be embedded and searched against.
        We include multiple representations for better search.
        """
        amount = tx.get("amount", 0)
        amount_type = "income" if amount > 0 else "expense"

        text = f"""
        Transaction on {tx.get('date', 'unknown date')}
        Description: {tx.get('description', 'unknown')}
        Amount: ${abs(amount):.2f} ({amount_type})
        Category: {tx.get('category', 'other')}
        Type: {tx.get('type', 'debit')}
        """

        return text.strip()

    def search(
        self,
        query: str,
        top_k: int = 10,
        category_filter: Optional[str] = None,
        file_id_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Search for relevant transactions using vector similarity

        Args:
            query: Natural language query
            top_k: Number of results to return
            category_filter: Filter by category (optional)
            file_id_filter: Filter by file_id (optional)

        Returns:
            List of matching transactions with relevance scores
        """
        if self.index is None:
            return []

        # Use retriever instead of query_engine (no LLM needed)
        retriever = self.index.as_retriever(
            similarity_top_k=top_k,
        )

        # Retrieve similar nodes
        nodes = retriever.retrieve(query)

        # Extract results
        results = []
        for node in nodes:
            metadata = node.metadata

            # Apply filters if specified
            if category_filter and metadata.get("category") != category_filter:
                continue
            if file_id_filter and metadata.get("file_id") != file_id_filter:
                continue

            results.append({
                "text": node.text,
                "score": node.score,
                **metadata
            })

        return results

    def delete_by_file_id(self, file_id: str) -> int:
        """
        Delete all transactions from a specific file

        Args:
            file_id: The file_id to delete

        Returns:
            Number of points deleted
        """
        try:
            # Delete from Qdrant using filter
            result = self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="file_id",
                            match=MatchValue(value=file_id)
                        )
                    ]
                )
            )
            print(f"✓ Deleted transactions for file_id: {file_id}")
            return 1  # Qdrant doesn't return count, so return 1 for success
        except Exception as e:
            print(f"✗ Error deleting file_id {file_id}: {e}")
            return 0

    def get_all_file_ids(self) -> List[str]:
        """Get list of all unique file_ids in the store"""
        try:
            # Scroll through all points to get file_ids
            records, _ = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                limit=10000,
                with_payload=True
            )

            file_ids = set()
            for record in records:
                if record.payload:
                    file_ids.add(record.payload.get("file_id", "unknown"))

            return list(file_ids)
        except Exception as e:
            print(f"Error getting file_ids: {e}")
            return []

    def get_collection_stats(self) -> Dict:
        """Get statistics about the collection"""
        try:
            info = self.qdrant_client.get_collection(self.collection_name)
            return {
                "total_points": info.points_count,
                "status": info.status.value if hasattr(info.status, 'value') else str(info.status)
            }
        except Exception as e:
            return {"error": str(e), "total_points": 0}

    def clear_all(self):
        """Delete all data in the collection and recreate with indexes"""
        try:
            self.qdrant_client.delete_collection(self.collection_name)
            self._init_collection()
            self._create_payload_indexes()
            self.index = None
            print(f"Cleared collection: {self.collection_name}")
        except Exception as e:
            print(f"Error clearing collection: {e}")

    def ensure_indexes(self):
        """Ensure payload indexes exist (call after connecting to existing collection)"""
        self._create_payload_indexes()


# ===================
# TEST
# ===================
if __name__ == "__main__":
    from config import (
        QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION,
        DEMO_CSV_PATH, CATEGORIES_PATH
    )
    from pdf_processor import load_demo_data
    from categorizer import TransactionCategorizer

    print("Testing Vector Store with Qdrant Cloud...")

    # Check config
    if not QDRANT_URL or not QDRANT_API_KEY:
        print("QDRANT_URL and QDRANT_API_KEY must be set in .env")
        exit(1)

    # Load and categorize demo data
    transactions = load_demo_data(str(DEMO_CSV_PATH))
    categorizer = TransactionCategorizer(str(CATEGORIES_PATH))
    categorized = categorizer.categorize_transactions(transactions)

    print(f"Loaded {len(categorized)} transactions")

    # Initialize vector store (connects to Qdrant Cloud)
    store = FinanceVectorStore(
        qdrant_url=QDRANT_URL,
        qdrant_api_key=QDRANT_API_KEY,
        collection_name=QDRANT_COLLECTION
    )

    # Clear existing data
    store.clear_all()

    # Add transactions
    added = store.add_transactions(categorized)
    print(f"Added {added} transactions to vector store")

    # Test search
    print("\nTesting search for 'coffee'...")
    results = store.search("coffee starbucks", top_k=5)

    for r in results:
        print(f"  [{r['score']:.3f}] {r['description']} - ${r['amount']:.2f}")

    # Get stats
    stats = store.get_collection_stats()
    print(f"\nCollection stats: {stats}")
