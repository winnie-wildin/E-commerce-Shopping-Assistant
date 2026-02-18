"""Shopping tools for the AI agent."""
import json
import asyncio
import logging
from typing import List, Optional

from langchain.tools import tool

from app.services.fakestore import FakeStoreClient
from app.models.product import Product

log = logging.getLogger("tools")

# ── Shared state ──

_fakestore_client: Optional[FakeStoreClient] = None


class _ToolContext:
    """
    Shared context for passing identity to tools.
    Set before the graph runs; tools execute sequentially within a single request.
    """
    conversation_id: str = "default"
    user_id: Optional[str] = None
    last_search_ids: set = set()  # product IDs from the most recent search


_context = _ToolContext()


def get_fakestore_client() -> FakeStoreClient:
    """Get or create Fake Store client instance"""
    global _fakestore_client
    if _fakestore_client is None:
        _fakestore_client = FakeStoreClient()
    return _fakestore_client


def _get_conversation_id() -> str:
    return _context.conversation_id


def _get_user_id() -> Optional[str]:
    return _context.user_id


def run_async(coro):
    """Helper to run async functions in sync context (for LangChain tools)"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an already-running loop (e.g. FastAPI) — use a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── Product Tools ──

@tool
def search_products(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
) -> str:
    """
    Search and filter products using semantic understanding. Can browse by category, search by natural language, filter by price, or combine all three.
    At least one parameter should be provided.

    Args:
        query: Optional natural-language search (e.g., "something for a party", "tech gadgets", "warm clothing")
        category: Optional category filter. Exact values: "electronics", "jewelery", "men's clothing", "women's clothing"
        max_price: Optional maximum price filter (e.g., 100.0 for products under $100)

    Returns:
        JSON string with list of matching products ranked by relevance
    """
    try:
        log.info(f"search_products called: query={query!r}, category={category!r}, max_price={max_price!r}")

        from app.services.vector_store import get_vector_store

        store = get_vector_store()

        if store and store.is_ready:
            if query:
                products = store.search(query, top_k=10, category=category, max_price=max_price)
                log.info(f"Semantic search found {len(products)} products")
            else:
                products = store.get_all_products(category=category, max_price=max_price)
                log.info(f"Category/filter browse found {len(products)} products")
        else:
            log.info("Vector store unavailable — falling back to keyword search")
            client = get_fakestore_client()
            products = run_async(client.search_products(query, category, max_price))
            log.info(f"Keyword search found {len(products)} products")

        result = []
        for product in products[:10]:
            result.append(
                {
                    "id": product.id,
                    "title": product.title,
                    "price": product.price,
                    "category": product.category,
                    "image": product.image,
                    "rating": f"{product.rating.rate} ({product.rating.count} reviews)",
                }
            )
            log.info(f"  -> #{product.id} {product.title} (${product.price})")

        if not result:
            log.info("  -> No matches after filtering")
            _context.last_search_ids = set()
            return json.dumps(
                {"message": "No products found matching your criteria.", "suggestion": "Try browsing by category or broadening your search."}
            )

        _context.last_search_ids = {p["id"] for p in result}
        return json.dumps({"count": len(result), "products": result}, indent=2)
    except Exception as e:
        log.error(f"search_products error: {e}")
        return json.dumps({"error": f"Failed to search products: {str(e)}"})


@tool
def get_categories() -> str:
    """
    Get all available product categories in the store.
    Use this to discover what categories exist before searching.

    Returns:
        JSON string with list of category names
    """
    try:
        from app.services.vector_store import get_vector_store
        
        store = get_vector_store()
        if store and store.is_ready:
            categories = store.get_all_categories()
            return json.dumps({"categories": categories})
        else:
            client = get_fakestore_client()
            categories = run_async(client.get_all_categories())
            return json.dumps({"categories": categories})
    except Exception as e:
        return json.dumps({"error": f"Failed to get categories: {str(e)}"})


@tool
def get_product_details(product_id: int) -> str:
    """
    Get detailed information about a specific product by its ID.
    IMPORTANT: Only use product IDs returned by a previous search_products call.

    Args:
        product_id: The ID of the product to retrieve details for (must come from search results)

    Returns:
        JSON string with complete product information
    """
    try:
        if _context.last_search_ids and product_id not in _context.last_search_ids:
            log.warning(
                f"get_product_details called with id={product_id} which was NOT in last search results {_context.last_search_ids}"
            )

        from app.services.vector_store import get_vector_store
        
        store = get_vector_store()
        if store and store.is_ready:
            product = store.get_product_by_id(product_id)
            if not product:
                return json.dumps({"error": f"Product #{product_id} not found. Use an ID from search_products results."})
        else:
            client = get_fakestore_client()
            product = run_async(client.get_product_by_id(product_id))

        log.info(f"get_product_details: #{product_id} '{product.title}'")

        return json.dumps(
            {
                "id": product.id,
                "title": product.title,
                "price": product.price,
                "description": product.description,
                "category": product.category,
                "image": product.image,
                "rating": {"rate": product.rating.rate, "count": product.rating.count},
            },
            indent=2,
        )
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "not found" in error_msg.lower():
            return json.dumps({"error": f"Product #{product_id} not found."})
        log.error(f"get_product_details error: {e}")
        return json.dumps({"error": f"Failed to get product details: {error_msg}"})


# ── Cart Tools (SQLite-backed) ──

def _cart_kwargs() -> dict:
    """Return the correct owner kwargs for DB helpers (user_id or conversation_id)."""
    uid = _get_user_id()
    if uid:
        return {"user_id": uid}
    return {"conversation_id": _get_conversation_id()}


async def _db_add_to_cart(product_id: int, quantity: int):
    """Async helper — adds item to cart in SQLite."""
    from app.services.database import async_session, add_cart_item, get_cart_total_items
    kw = _cart_kwargs()

    async with async_session() as session:
        async with session.begin():
            row = await add_cart_item(session, product_id=product_id, quantity=quantity, **kw)
            total = await get_cart_total_items(session, **kw)
            return row.quantity, total


async def _db_get_cart():
    """Async helper — reads cart from SQLite."""
    from app.services.database import async_session, get_cart_items
    kw = _cart_kwargs()

    async with async_session() as session:
        items = await get_cart_items(session, **kw)
        return [(item.product_id, item.quantity) for item in items]


async def _db_remove_from_cart(product_id: int) -> bool:
    """Async helper — removes item from cart in SQLite."""
    from app.services.database import async_session, remove_cart_item
    kw = _cart_kwargs()

    async with async_session() as session:
        async with session.begin():
            return await remove_cart_item(session, product_id=product_id, **kw)


@tool
def add_to_cart(product_id: int, quantity: int = 1) -> str:
    """
    Add a product to the shopping cart with specified quantity.

    Args:
        product_id: The ID of the product to add
        quantity: Number of items to add (default: 1)

    Returns:
        JSON string with confirmation message
    """
    try:
        if quantity < 1:
            return json.dumps({"error": "Quantity must be at least 1."})

        # Validate product exists
        from app.services.vector_store import get_vector_store
        store = get_vector_store()
        
        if store and store.is_ready:
            product = store.get_product_by_id(product_id)
            if not product:
                return json.dumps({"error": f"Product #{product_id} not found."})
        else:
            client = get_fakestore_client()
            try:
                product = run_async(client.get_product_by_id(product_id))
            except Exception as e:
                error_msg = str(e)
                if "404" in error_msg or "not found" in error_msg.lower():
                    return json.dumps({"error": f"Product #{product_id} not found."})
                raise

        # Persist to SQLite (uses user_id if logged in, else conversation_id)
        qty_in_cart, total_items = run_async(_db_add_to_cart(product_id, quantity))

        log.info(f"add_to_cart: +{quantity} x #{product_id} '{product.title}' -> cart has {total_items} total items")

        return json.dumps(
            {
                "message": f"Added {quantity} x {product.title} to cart",
                "product_id": product_id,
                "product_title": product.title,
                "quantity_in_cart": qty_in_cart,
                "total_items": total_items,
            },
            indent=2,
        )
    except Exception as e:
        log.error(f"add_to_cart error: {e}")
        return json.dumps({"error": f"Failed to add to cart: {str(e)}"})


@tool
def get_cart() -> str:
    """
    Retrieve the current shopping cart contents for this conversation.

    Returns:
        JSON string with cart items, quantities, and total price
    """
    try:
        cart_rows = run_async(_db_get_cart())

        if not cart_rows:
            return json.dumps({"message": "Your cart is empty.", "items": [], "total": 0.0})

        from app.services.vector_store import get_vector_store
        store = get_vector_store()
        
        items = []
        total = 0.0
        for pid, qty in cart_rows:
            if store and store.is_ready:
                product = store.get_product_by_id(pid)
                if not product:
                    log.warning(f"Product #{pid} not found in store, skipping")
                    continue
            else:
                client = get_fakestore_client()
                product = run_async(client.get_product_by_id(pid))
            
            subtotal = product.price * qty
            total += subtotal
            items.append(
                {
                    "product_id": pid,
                    "title": product.title,
                    "price": product.price,
                    "quantity": qty,
                    "subtotal": round(subtotal, 2),
                }
            )

        log.info(f"get_cart: {len(items)} items, total=${total:.2f}")

        return json.dumps(
            {"items": items, "total": round(total, 2), "item_count": len(items)},
            indent=2,
        )
    except Exception as e:
        log.error(f"get_cart error: {e}")
        return json.dumps({"error": f"Failed to get cart: {str(e)}"})


@tool
def remove_from_cart(product_id: int) -> str:
    """
    Remove a product from the shopping cart entirely.

    Args:
        product_id: The ID of the product to remove

    Returns:
        JSON string with confirmation message
    """
    try:
        removed = run_async(_db_remove_from_cart(product_id))

        if not removed:
            return json.dumps({"error": f"Product #{product_id} is not in your cart."})

        from app.services.vector_store import get_vector_store
        store = get_vector_store()
        
        if store and store.is_ready:
            product = store.get_product_by_id(product_id)
            if not product:
                return json.dumps({"error": f"Product #{product_id} not found."})
        else:
            client = get_fakestore_client()
            product = run_async(client.get_product_by_id(product_id))

        # Check remaining items
        remaining = run_async(_db_get_cart())

        log.info(f"remove_from_cart: removed #{product_id} '{product.title}', {len(remaining)} items left")

        if not remaining:
            return json.dumps({"message": f"Removed {product.title}. Cart is now empty."})

        return json.dumps(
            {"message": f"Removed {product.title} from cart", "remaining_items": len(remaining)},
            indent=2,
        )
    except Exception as e:
        log.error(f"remove_from_cart error: {e}")
        return json.dumps({"error": f"Failed to remove from cart: {str(e)}"})


# Export all tools
__all__ = [
    "search_products",
    "get_product_details",
    "get_categories",
    "add_to_cart",
    "get_cart",
    "remove_from_cart",
]
