# E-commerce Shopping Assistant

Conversational shopping assistant built with Next.js 16, FastAPI, LangGraph, and FAISS.

## Setup

See [SETUP.md](SETUP.md) for Docker and manual setup instructions.

```bash
# configure backend/.env and frontend/.env.local first (see SETUP.md)
docker compose up --build
```
http://localhost:3000

## Architecture

| Layer | Stack |
|---|---|
| Frontend | Next.js 16 (App Router), TailwindCSS, SSE streaming, NextAuth.js (Google OAuth) |
| Backend | FastAPI, LangGraph StateGraph, GPT-4 Turbo, FAISS + OpenAI embeddings |
| Storage | SQLite (async SQLAlchemy), persistent FAISS index on disk |
| Infra | Docker Compose |

```
frontend/
  app/api/auth/          NextAuth.js route
  components/auth/       AuthButton, AuthProvider
  components/chat/       ChatInterface, MessageList, ProductCard
  lib/auth.ts            NextAuth config (Google provider)
  lib/api.ts             API client, SSE stream parser

backend/
  app/main.py            FastAPI entry, lifespan (DB + FAISS init)
  app/routes/chat.py     POST /api/chat, SSE streaming
  app/services/
    agent.py             LangGraph StateGraph
    database.py          SQLite persistence
    vector_store.py      FAISS index, embeddings, disk persistence
    fakestore.py         Fake Store API client
  app/tools/shopping_tools.py   6 tools (5 required + get_categories)
  tests/                 50 tests

docker-compose.yml
```

## Agent Design

Two-node LangGraph `StateGraph`: an LLM node (GPT-4 Turbo with 6 bound tools) and a `ToolNode` for execution. After each LLM turn, a conditional edge checks for tool calls. If present, execute and loop back; otherwise, terminate. Responses stream as structured SSE events (`tool_start`, `products`, `token`, `cart`) so the frontend renders product cards and cart state incrementally instead of waiting for the full response.

```
START -> agent (LLM) -> tool_calls? --yes--> tools -> agent (loop)
                            \--no--> END
```

### Design Decisions

**LangGraph over AgentExecutor.** `AgentExecutor` is a black box. Explicit `StateGraph` makes routing visible, testable, and extensible. Adding a reviewer node or human-in-the-loop is a graph change, not a framework workaround.

**FAISS `IndexFlatIP` over approximate methods (IVF/HNSW).** With ~20 products, exact search is the right call. Approximate indices add training steps that only pay off past ~100k vectors. Vectors are L2-normalized so inner product = cosine similarity.

**Embedding construction: title + description + category.** Title alone loses too much signal. Product descriptions in this dataset carry most of the semantic weight for intent matching. Category as a text suffix gives the model a soft hint before hard post-filtering applies.

**Persistent FAISS index.** First startup fetches from Fake Store API, embeds everything, and writes the index + product JSON to disk. After that, startup loads from disk (~100ms vs ~3s). No API dependency after the first run, no recomputing embeddings.

**Cart scoped to user ID or conversation ID.** Authenticated users (Google OAuth) get carts tied to their email, persistent across sessions and restarts. Anonymous users get carts scoped to conversation UUID, which keeps things stateless from the frontend's perspective while still persisting across tool calls within a session.

**SSE streaming.** Structured JSON events (`tool_start`, `products`, `token`, `cart`) let the frontend distinguish tool activity from LLM tokens without heuristics.

### What I'd Change at Scale

- Replace FAISS with a hosted vector DB (Pinecone, Weaviate) to avoid loading the full index into process memory and to support incremental updates without a full rebuild.
- Postgres + connection pooling. SQLite's single-writer lock breaks under concurrent users.
- Rate limiting and token budgets per user. OpenAI calls are unbounded right now.
- LRU cache on embedding queries. Repeated or near-identical searches currently recompute embeddings every time.
- Task queue (Celery, Dramatiq) for agent calls. Under load, synchronous tool execution in the graph loop ties up request workers.

## Testing

```bash
cd backend
pytest tests/ -v
```

50 tests: `test_tools.py` (34) + `test_database.py` (16).
Test infra uses `respx` to mock the Fake Store API and in-memory SQLite per test.

## API

**POST /api/chat**

```json
{ "message": "Show me electronics under $100", "conversation_id": "conv_123" }
```

Response is an SSE stream:
```
data: {"type": "tool_start", "tool": "search_products"}
data: {"type": "products", "data": [...]}
data: {"type": "token", "content": "Here are..."}
data: [DONE]
```

**GET /health** health check
**GET /docs** Swagger UI

## Environment Variables

Backend (`backend/.env`):
- `OPENAI_API_KEY` (required)

Frontend (`frontend/.env.local`):
- `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (optional, for Google sign-in)
- `NEXTAUTH_URL` (default `http://localhost:3000`)
- `NEXTAUTH_SECRET` (required when using auth)

## Dependencies

Backend: fastapi, uvicorn, langchain, langchain-openai, langgraph, faiss-cpu, sqlalchemy[asyncio], aiosqlite, httpx, tenacity, pytest

Frontend: next 16, react 19, next-auth 4, typescript, tailwindcss 4, lucide-react, shadcn/ui
