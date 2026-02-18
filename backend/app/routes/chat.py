"""
Chat API routes — conversation history persisted in SQLite.
"""
import os
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.models.chat import ChatRequest, ChatMessage
from app.services.agent import get_agent
from app.services.database import async_session, add_message, get_messages, get_or_create_conversation

router = APIRouter()


def check_api_key() -> bool:
    """Check if OpenAI API key is available and valid"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return False
    api_key = api_key.strip()
    if not api_key or api_key == "your_openai_api_key_here":
        return False
    if len(api_key) < 10:
        return False
    return True


@router.post("/chat")
async def chat_endpoint(request: ChatRequest, raw_request: Request):
    """Chat endpoint - streaming responses with structured SSE events"""
    if not check_api_key():
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is missing or invalid. Please check your .env file."
        )

    try:
        agent = get_agent()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Agent initialization failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent service error: {str(e)}")

    conversation_id = request.conversation_id or "default"
    user_id = raw_request.headers.get("X-User-Id") or None

    # Load history from DB
    async with async_session() as session:
        async with session.begin():
            await get_or_create_conversation(session, conversation_id)
            db_messages = await get_messages(session, conversation_id, limit=20)
            history = [ChatMessage(role=m.role, content=m.content) for m in db_messages]

            # Persist the user message
            await add_message(session, conversation_id, "user", request.message)

    async def generate_response():
        try:
            assistant_response = ""
            async for chunk in agent.process_message(
                request.message,
                history,
                conversation_id,
                user_id=user_id,
            ):
                # Extract text tokens for the response we'll persist
                try:
                    event = json.loads(chunk)
                    if event.get("type") == "token":
                        assistant_response += event.get("content", "")
                except (json.JSONDecodeError, TypeError):
                    pass

                yield f"data: {chunk}\n\n".encode("utf-8")

            # Persist the assistant response
            if assistant_response:
                async with async_session() as session:
                    async with session.begin():
                        await add_message(session, conversation_id, "assistant", assistant_response)

            yield "data: [DONE]\n\n".encode("utf-8")
        except Exception as e:
            error_event = json.dumps({"type": "token", "content": f"Error: {str(e)}"})
            yield f"data: {error_event}\n\n".encode("utf-8")
            yield "data: [DONE]\n\n".encode("utf-8")

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
