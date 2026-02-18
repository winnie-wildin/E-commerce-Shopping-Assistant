"""
SQLite persistence layer using SQLAlchemy async.

Provides:
- Async engine + session factory
- SQLAlchemy ORM models (Conversation, Message, CartItem)
- CRUD helpers used by the chat route and shopping tools
"""
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
    delete,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

log = logging.getLogger("database")

# ── Database path ──
# Default: backend/data/shopping_assistant.db
_backend_dir = Path(__file__).resolve().parent.parent.parent
_data_dir = _backend_dir / "data"
_data_dir.mkdir(exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{_data_dir / 'shopping_assistant.db'}",
)

# ── Engine & Session ──

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Base ──

class Base(DeclarativeBase):
    pass


# ── ORM Models ──

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)  # UUID from frontend
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    cart_items = relationship("CartItemRow", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="messages")


class CartItemRow(Base):
    """One row per (owner, product) pair — owner is user_id (logged in) or conversation_id (guest)."""
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="cart_items")


# ── Lifecycle ──

async def init_db():
    """Create all tables (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info(f"Database ready: {DATABASE_URL}")


async def close_db():
    """Dispose engine on shutdown."""
    await engine.dispose()


# ── CRUD: Conversations & Messages ──

async def get_or_create_conversation(session: AsyncSession, conversation_id: str) -> Conversation:
    """Return existing conversation or create a new one."""
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    convo = result.scalar_one_or_none()
    if convo is None:
        convo = Conversation(id=conversation_id)
        session.add(convo)
        await session.flush()
    return convo


async def add_message(session: AsyncSession, conversation_id: str, role: str, content: str) -> Message:
    """Append a message to a conversation."""
    await get_or_create_conversation(session, conversation_id)
    msg = Message(conversation_id=conversation_id, role=role, content=content)
    session.add(msg)
    await session.flush()
    return msg


async def get_messages(session: AsyncSession, conversation_id: str, limit: int = 20) -> List[Message]:
    """Retrieve the most recent messages for a conversation."""
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()  # chronological order
    return rows


# ── CRUD: Cart ──
# All cart helpers accept user_id (logged-in) OR conversation_id (guest).

def _cart_owner_filter(*, user_id: Optional[str] = None, conversation_id: Optional[str] = None):
    """Return a SQLAlchemy filter clause for the cart owner."""
    if user_id:
        return CartItemRow.user_id == user_id
    return CartItemRow.conversation_id == conversation_id


async def get_cart_items(
    session: AsyncSession,
    conversation_id: Optional[str] = None,
    *,
    user_id: Optional[str] = None,
) -> List[CartItemRow]:
    """Return all cart items for a user or conversation."""
    result = await session.execute(
        select(CartItemRow).where(_cart_owner_filter(user_id=user_id, conversation_id=conversation_id))
    )
    return list(result.scalars().all())


async def add_cart_item(
    session: AsyncSession,
    conversation_id: Optional[str] = None,
    product_id: int = 0,
    quantity: int = 1,
    *,
    user_id: Optional[str] = None,
) -> CartItemRow:
    """Add to cart — increments quantity if the product is already there."""
    if conversation_id:
        await get_or_create_conversation(session, conversation_id)

    owner = _cart_owner_filter(user_id=user_id, conversation_id=conversation_id)
    result = await session.execute(
        select(CartItemRow).where(owner, CartItemRow.product_id == product_id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.quantity += quantity
    else:
        row = CartItemRow(
            user_id=user_id,
            conversation_id=conversation_id if not user_id else None,
            product_id=product_id,
            quantity=quantity,
        )
        session.add(row)
    await session.flush()
    return row


async def remove_cart_item(
    session: AsyncSession,
    conversation_id: Optional[str] = None,
    product_id: int = 0,
    *,
    user_id: Optional[str] = None,
) -> bool:
    """Remove a product from the cart entirely. Returns True if it existed."""
    owner = _cart_owner_filter(user_id=user_id, conversation_id=conversation_id)
    result = await session.execute(
        delete(CartItemRow).where(owner, CartItemRow.product_id == product_id)
    )
    return result.rowcount > 0


async def get_cart_total_items(
    session: AsyncSession,
    conversation_id: Optional[str] = None,
    *,
    user_id: Optional[str] = None,
) -> int:
    """Sum of all quantities in the cart."""
    owner = _cart_owner_filter(user_id=user_id, conversation_id=conversation_id)
    result = await session.execute(
        select(func.coalesce(func.sum(CartItemRow.quantity), 0)).where(owner)
    )
    return result.scalar_one()
