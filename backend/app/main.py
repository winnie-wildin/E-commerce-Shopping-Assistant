"""
FastAPI application entry point
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logging.getLogger("tools").setLevel(logging.INFO)
logging.getLogger("database").setLevel(logging.INFO)

# Load environment variables FIRST, before any other imports
# Explicitly look for .env in the backend directory (parent of app/)
backend_dir = Path(__file__).parent.parent
env_path = backend_dir / ".env"
load_dotenv(dotenv_path=env_path, override=True)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle — init DB + FAISS index on boot."""
    from app.services.database import init_db, close_db
    from app.services.vector_store import initialize_vector_store

    await init_db()
    await initialize_vector_store()
    yield
    await close_db()


app = FastAPI(
    title="E-commerce Shopping Assistant API",
    description="AI-powered shopping assistant backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - allow frontend to communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router, prefix="/api", tags=["chat"])


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "service": "E-commerce Shopping Assistant API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat (POST)",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "shopping-assistant-api"}
