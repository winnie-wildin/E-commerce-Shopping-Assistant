"""
Unit tests for the SQLite persistence layer (database.py).

Tests conversation, message, and cart CRUD operations
against an in-memory SQLite DB (swapped in via conftest.py).
"""
import pytest
import pytest_asyncio

import app.services.database as db_mod
from app.services.database import (
    get_or_create_conversation,
    add_message,
    get_messages,
    get_cart_items,
    add_cart_item,
    remove_cart_item,
    get_cart_total_items,
    Conversation,
    Message,
    CartItemRow,
)

def _session():
    """Access the (potentially monkey-patched) session factory at call time."""
    return db_mod.async_session


# ═══════════════════════════════════════════
# Conversation CRUD
# ═══════════════════════════════════════════


class TestConversations:

    @pytest.mark.asyncio
    async def test_create_conversation(self):
        async with _session()() as session:
            async with session.begin():
                convo = await get_or_create_conversation(session, "conv-1")
                assert convo.id == "conv-1"

    @pytest.mark.asyncio
    async def test_get_existing_conversation(self):
        async with _session()() as session:
            async with session.begin():
                await get_or_create_conversation(session, "conv-2")

        async with _session()() as session:
            async with session.begin():
                convo = await get_or_create_conversation(session, "conv-2")
                assert convo.id == "conv-2"

    @pytest.mark.asyncio
    async def test_separate_conversations(self):
        async with _session()() as session:
            async with session.begin():
                c1 = await get_or_create_conversation(session, "conv-a")
                c2 = await get_or_create_conversation(session, "conv-b")
                assert c1.id != c2.id


# ═══════════════════════════════════════════
# Message CRUD
# ═══════════════════════════════════════════


class TestMessages:

    @pytest.mark.asyncio
    async def test_add_and_get_messages(self):
        async with _session()() as session:
            async with session.begin():
                await add_message(session, "msg-test", "user", "Hello")
                await add_message(session, "msg-test", "assistant", "Hi there!")

        async with _session()() as session:
            msgs = await get_messages(session, "msg-test")
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert msgs[0].content == "Hello"
            assert msgs[1].role == "assistant"
            assert msgs[1].content == "Hi there!"

    @pytest.mark.asyncio
    async def test_messages_ordered_chronologically(self):
        async with _session()() as session:
            async with session.begin():
                await add_message(session, "order-test", "user", "First")
                await add_message(session, "order-test", "assistant", "Second")
                await add_message(session, "order-test", "user", "Third")

        async with _session()() as session:
            msgs = await get_messages(session, "order-test")
            contents = [m.content for m in msgs]
            assert contents == ["First", "Second", "Third"]

    @pytest.mark.asyncio
    async def test_messages_limit(self):
        async with _session()() as session:
            async with session.begin():
                for i in range(25):
                    await add_message(session, "limit-test", "user", f"Message {i}")

        async with _session()() as session:
            msgs = await get_messages(session, "limit-test", limit=10)
            assert len(msgs) == 10
            # Should be the LAST 10 messages (most recent)
            assert msgs[-1].content == "Message 24"

    @pytest.mark.asyncio
    async def test_messages_isolated_per_conversation(self):
        async with _session()() as session:
            async with session.begin():
                await add_message(session, "iso-a", "user", "For A")
                await add_message(session, "iso-b", "user", "For B")

        async with _session()() as session:
            msgs_a = await get_messages(session, "iso-a")
            msgs_b = await get_messages(session, "iso-b")
            assert len(msgs_a) == 1
            assert len(msgs_b) == 1
            assert msgs_a[0].content == "For A"
            assert msgs_b[0].content == "For B"

    @pytest.mark.asyncio
    async def test_empty_conversation_messages(self):
        async with _session()() as session:
            msgs = await get_messages(session, "nonexistent")
            assert msgs == []


# ═══════════════════════════════════════════
# Cart CRUD
# ═══════════════════════════════════════════


class TestCartDatabase:

    @pytest.mark.asyncio
    async def test_add_cart_item(self):
        async with _session()() as session:
            async with session.begin():
                row = await add_cart_item(session, "cart-1", product_id=1, quantity=2)
                assert row.product_id == 1
                assert row.quantity == 2

    @pytest.mark.asyncio
    async def test_add_cart_item_increments(self):
        async with _session()() as session:
            async with session.begin():
                await add_cart_item(session, "cart-inc", product_id=5, quantity=1)
                row = await add_cart_item(session, "cart-inc", product_id=5, quantity=3)
                assert row.quantity == 4  # 1 + 3

    @pytest.mark.asyncio
    async def test_get_cart_items(self):
        async with _session()() as session:
            async with session.begin():
                await add_cart_item(session, "cart-get", product_id=1, quantity=1)
                await add_cart_item(session, "cart-get", product_id=9, quantity=2)

        async with _session()() as session:
            items = await get_cart_items(session, "cart-get")
            assert len(items) == 2
            ids = {item.product_id for item in items}
            assert ids == {1, 9}

    @pytest.mark.asyncio
    async def test_get_empty_cart(self):
        async with _session()() as session:
            items = await get_cart_items(session, "empty-cart")
            assert items == []

    @pytest.mark.asyncio
    async def test_remove_cart_item(self):
        async with _session()() as session:
            async with session.begin():
                await add_cart_item(session, "cart-rm", product_id=1, quantity=1)

        async with _session()() as session:
            async with session.begin():
                removed = await remove_cart_item(session, "cart-rm", product_id=1)
                assert removed is True

        async with _session()() as session:
            items = await get_cart_items(session, "cart-rm")
            assert len(items) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_item(self):
        async with _session()() as session:
            async with session.begin():
                removed = await remove_cart_item(session, "cart-rm2", product_id=999)
                assert removed is False

    @pytest.mark.asyncio
    async def test_cart_total_items(self):
        async with _session()() as session:
            async with session.begin():
                await add_cart_item(session, "cart-total", product_id=1, quantity=2)
                await add_cart_item(session, "cart-total", product_id=9, quantity=3)
                total = await get_cart_total_items(session, "cart-total")
                assert total == 5

    @pytest.mark.asyncio
    async def test_cart_isolated_per_conversation(self):
        async with _session()() as session:
            async with session.begin():
                await add_cart_item(session, "cart-iso-a", product_id=1, quantity=1)
                await add_cart_item(session, "cart-iso-b", product_id=9, quantity=1)

        async with _session()() as session:
            items_a = await get_cart_items(session, "cart-iso-a")
            items_b = await get_cart_items(session, "cart-iso-b")
            assert len(items_a) == 1
            assert items_a[0].product_id == 1
            assert len(items_b) == 1
            assert items_b[0].product_id == 9
