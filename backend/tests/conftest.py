"""
Shared fixtures for the test suite.

Key design decisions:
- Uses respx to mock all Fake Store API calls (no real HTTP).
- Uses an in-memory SQLite DB per test session (fast, isolated).
- Resets tool-level state between tests.
"""
import os
import json
import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
import respx
import httpx

# Ensure env is loaded before anything else
from dotenv import load_dotenv

backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=backend_dir / ".env", override=True)

# ── Fake product catalog ──

FAKE_PRODUCTS = [
    {
        "id": 1,
        "title": "Fjallraven Backpack",
        "price": 109.95,
        "description": "Your perfect pack for everyday use.",
        "category": "men's clothing",
        "image": "https://fakestoreapi.com/img/81fPKd-2AYL._AC_SL1500_.jpg",
        "rating": {"rate": 3.9, "count": 120},
    },
    {
        "id": 2,
        "title": "Mens Casual T-Shirt",
        "price": 22.3,
        "description": "Slim-fitting style in a durable fabric.",
        "category": "men's clothing",
        "image": "https://fakestoreapi.com/img/71-3HjGNDUL._AC_SY879._SX._UX._SY._UY_.jpg",
        "rating": {"rate": 4.1, "count": 259},
    },
    {
        "id": 9,
        "title": "WD 2TB External Hard Drive",
        "price": 64.0,
        "description": "USB 3.0 portable storage.",
        "category": "electronics",
        "image": "https://fakestoreapi.com/img/61IBBVJvSDL._AC_SY879_.jpg",
        "rating": {"rate": 3.3, "count": 203},
    },
    {
        "id": 14,
        "title": "Samsung 49-Inch Gaming Monitor",
        "price": 999.99,
        "description": "Super ultra-wide curved gaming monitor.",
        "category": "electronics",
        "image": "https://fakestoreapi.com/img/81Zt42ioCgL._AC_SX679_.jpg",
        "rating": {"rate": 2.2, "count": 140},
    },
    {
        "id": 7,
        "title": "White Gold Plated Princess Ring",
        "price": 9.99,
        "description": "Classic ring for special occasions.",
        "category": "jewelery",
        "image": "https://fakestoreapi.com/img/71YAIFU48IL._AC_UL640_QL65_ML3_.jpg",
        "rating": {"rate": 3.0, "count": 400},
    },
]

FAKE_CATEGORIES = ["electronics", "jewelery", "men's clothing", "women's clothing"]


def _product_by_id(pid: int):
    for p in FAKE_PRODUCTS:
        if p["id"] == pid:
            return p
    return None


# ── respx mock setup ──


@pytest.fixture(autouse=True)
def mock_fakestore_api():
    """Intercept all HTTP calls to fakestoreapi.com and return canned data."""
    with respx.mock(assert_all_called=False) as router:
        base = "https://fakestoreapi.com"

        # GET /products
        router.get(f"{base}/products").mock(
            return_value=httpx.Response(200, json=FAKE_PRODUCTS)
        )

        # GET /products/categories
        router.get(f"{base}/products/categories").mock(
            return_value=httpx.Response(200, json=FAKE_CATEGORIES)
        )

        # GET /products/category/:cat
        for cat in FAKE_CATEGORIES:
            cat_products = [p for p in FAKE_PRODUCTS if p["category"] == cat]
            router.get(f"{base}/products/category/{cat}").mock(
                return_value=httpx.Response(200, json=cat_products)
            )

        # GET /products/:id — dynamic by product ID
        for p in FAKE_PRODUCTS:
            router.get(f"{base}/products/{p['id']}").mock(
                return_value=httpx.Response(200, json=p)
            )

        # Products that don't exist → 404
        router.get(url__regex=rf"{base}/products/\d+").mock(
            return_value=httpx.Response(404, json={"message": "not found"})
        )

        yield router


# ── In-memory SQLite for tests ──


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    """
    Swap the DB engine to an in-memory SQLite before each test,
    create tables, and tear down after.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.services import database as db_mod

    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # Monkey-patch the module
    original_engine = db_mod.engine
    original_session = db_mod.async_session
    db_mod.engine = test_engine
    db_mod.async_session = test_session_factory

    async with test_engine.begin() as conn:
        await conn.run_sync(db_mod.Base.metadata.create_all)

    yield

    # Teardown
    await test_engine.dispose()
    db_mod.engine = original_engine
    db_mod.async_session = original_session


# ── Reset tool state between tests ──


@pytest.fixture(autouse=True)
def reset_tool_state():
    """Reset shared state in shopping_tools between tests."""
    import app.tools.shopping_tools as tools_mod

    # Reset conversation context
    tools_mod._context.conversation_id = "test-conversation"

    # Reset fakestore client so each test gets a fresh one
    tools_mod._fakestore_client = None

    yield

    tools_mod._fakestore_client = None


# ── Disable vector store for tool tests ──


@pytest.fixture(autouse=True)
def disable_vector_store(monkeypatch):
    """
    Disable the vector store in tool tests so search_products
    falls back to keyword search (which uses our mocked API).
    """
    import app.services.vector_store as vs_mod
    monkeypatch.setattr(vs_mod, "_store", None)
