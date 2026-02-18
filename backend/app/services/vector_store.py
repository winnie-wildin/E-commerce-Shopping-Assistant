"""
Semantic product search using FAISS + OpenAI embeddings.

Persists FAISS index and product data to disk. Loads from disk on startup,
or fetches from Fake Store API if not available.
"""
import os
import json
import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
import faiss
from langchain_openai import OpenAIEmbeddings

from app.models.product import Product
from app.services.fakestore import FakeStoreClient

log = logging.getLogger("vector_store")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Persistence paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
FAISS_INDEX_PATH = DATA_DIR / "faiss_index.bin"
PRODUCTS_JSON_PATH = DATA_DIR / "products.json"


class ProductVectorStore:
    """FAISS-backed vector store for semantic product search with persistence"""

    def __init__(self):
        self._index: Optional[faiss.IndexFlatIP] = None
        self._products: List[Product] = []
        self._embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )

    @property
    def is_ready(self) -> bool:
        return self._index is not None and len(self._products) > 0

    def _save_to_disk(self):
        """Save FAISS index and products to disk."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save FAISS index
        if self._index is not None:
            faiss.write_index(self._index, str(FAISS_INDEX_PATH))
            log.info(f"Saved FAISS index to {FAISS_INDEX_PATH}")
        
        # Save products as JSON
        products_data = [p.model_dump() for p in self._products]
        with open(PRODUCTS_JSON_PATH, "w") as f:
            json.dump(products_data, f, indent=2)
        log.info(f"Saved {len(self._products)} products to {PRODUCTS_JSON_PATH}")

    def _load_from_disk(self) -> bool:
        """Load FAISS index and products from disk. Returns True if successful."""
        if not FAISS_INDEX_PATH.exists() or not PRODUCTS_JSON_PATH.exists():
            return False
        
        try:
            # Load FAISS index
            self._index = faiss.read_index(str(FAISS_INDEX_PATH))
            log.info(f"Loaded FAISS index from {FAISS_INDEX_PATH}")
            
            # Load products
            with open(PRODUCTS_JSON_PATH, "r") as f:
                products_data = json.load(f)
            self._products = [Product(**p) for p in products_data]
            log.info(f"Loaded {len(self._products)} products from {PRODUCTS_JSON_PATH}")
            
            return True
        except Exception as e:
            log.warning(f"Failed to load from disk: {e}")
            return False

    async def initialize(self):
        """Load from disk if available, otherwise fetch from API and build index."""
        # Try loading from disk first
        if self._load_from_disk():
            log.info("Vector store loaded from disk")
            return
        
        # Otherwise, fetch from API and build
        log.info("Building product vector index from API...")
        client = FakeStoreClient()
        try:
            self._products = await client.get_all_products()
        finally:
            await client.close()

        # Build descriptive text for each product
        texts = [
            f"{p.title}. {p.description}. Category: {p.category}"
            for p in self._products
        ]

        # Embed all products in one async batch call
        vectors = await self._embeddings.aembed_documents(texts)
        matrix = np.array(vectors, dtype=np.float32)

        # Normalize vectors so inner-product == cosine similarity
        faiss.normalize_L2(matrix)

        # Build FAISS index (Inner Product on normalized vectors)
        self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._index.add(matrix)

        # Save to disk for next time
        self._save_to_disk()
        log.info(f"Vector index ready: {len(self._products)} products indexed")

    # ── Search Methods ──

    def search(
        self,
        query: str,
        top_k: int = 10,
        category: Optional[str] = None,
        max_price: Optional[float] = None,
        min_score: float = 0.10,
    ) -> List[Product]:
        """Semantic search — returns products ranked by cosine similarity."""
        if not self.is_ready:
            raise RuntimeError("Vector store not initialized")

        query_vec = np.array(
            [self._embeddings.embed_query(query)], dtype=np.float32
        )
        faiss.normalize_L2(query_vec)

        # Search all products, then filter + rank
        scores, indices = self._index.search(query_vec, len(self._products))

        log.debug(f"Top-5 raw scores: {list(zip(scores[0][:5], indices[0][:5]))}")

        results: List[Product] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or score < min_score:
                continue
            product = self._products[idx]
            if category and product.category.lower() != category.lower():
                continue
            if max_price is not None and product.price > max_price:
                continue
            results.append(product)
            if len(results) >= top_k:
                break

        return results

    def get_all_products(
        self,
        category: Optional[str] = None,
        max_price: Optional[float] = None,
    ) -> List[Product]:
        """Return cached products with optional filters (no semantic search)."""
        products = self._products
        if category:
            products = [p for p in products if p.category.lower() == category.lower()]
        if max_price is not None:
            products = [p for p in products if p.price <= max_price]
        return products

    def get_product_by_id(self, product_id: int) -> Optional[Product]:
        """Get a product by ID from cached products."""
        for product in self._products:
            if product.id == product_id:
                return product
        return None

    def get_all_categories(self) -> List[str]:
        """Get all unique categories from cached products."""
        categories = set(p.category for p in self._products)
        return sorted(list(categories))


# ── Singleton ──

_store: Optional[ProductVectorStore] = None


def get_vector_store() -> Optional[ProductVectorStore]:
    return _store


async def initialize_vector_store():
    """Called once at app startup."""
    global _store
    try:
        _store = ProductVectorStore()
        await _store.initialize()
    except Exception as e:
        log.error(f"Vector store init failed (falling back to keyword search): {e}")
        _store = None
