"""
Chat-related Pydantic models
"""
from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str
    conversation_id: Optional[str] = None


class ChatMessage(BaseModel):
    """Chat message model"""
    role: str  # "user" or "assistant"
    content: str
