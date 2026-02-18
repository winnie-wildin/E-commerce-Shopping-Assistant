"""
AI Agent orchestration using LangGraph.

Implements a stateful graph with explicit routing between the LLM
and tool execution nodes, replacing the generic create_agent helper.

Graph topology:
    START → agent → should_continue?
                      ├─ tool_calls → tools → agent  (loop)
                      └─ no calls   → END
"""
import os
import json
from typing import Annotated, AsyncIterator, List, Optional, Sequence, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    AIMessageChunk,
    ToolMessage,
    SystemMessage,
)
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.tools.shopping_tools import (
    search_products,
    get_product_details,
    get_categories,
    add_to_cart,
    get_cart,
    remove_from_cart,
)
from app.models.chat import ChatMessage


# ── Agent State ──

class AgentState(TypedDict):
    """Typed state that flows through every node in the graph."""
    messages: Annotated[Sequence[AnyMessage], add_messages]


# ── System Prompt ──

SYSTEM_PROMPT = """You are a helpful and friendly shopping assistant for an e-commerce store.

Your role is to help users:
- Search and discover products using semantic understanding
- Compare products and provide recommendations
- Manage their shopping cart
- Answer questions about products

Guidelines:
- Always be conversational and friendly
- When showing products, include key details: name, price, category, and rating
- Format product information clearly and make it easy to read
- Help users make informed decisions
- If a user asks to compare products, provide a clear side-by-side comparison
- When adding items to cart, confirm the action clearly
- If a user asks about their cart, show all items with quantities and total price
- If you don't have enough information, ask clarifying questions
- Always use the available tools to get real product data - never make up product information

IMPORTANT tool-calling rules:
- search_products uses SEMANTIC SEARCH — it understands meaning, not just keywords. \
Feel free to use natural language queries like "something for a party" or "affordable tech gadgets".
- search_products results are DISPLAYED as visual product cards to the user. \
Only call it when you actually want the user to browse a LIST of products.
- RECOMMENDATION RULE: When recommending specific products, call get_product_details on each \
product you want to highlight AFTER searching. Each detail card is shown alongside your text. \
NEVER just describe a product in text if you can show its detail card instead.
- CRITICAL — PRODUCT IDs: You MUST only use product IDs that were returned by a previous \
search_products call in the SAME conversation turn. NEVER guess, assume, or recall product IDs \
from memory. If you haven't searched yet, search first, then use the exact IDs from the results.
- For questions about a SPECIFIC product (details, "most expensive", "cheapest", etc.), \
call search_products to find it, then call get_product_details on that ONE product.
- To browse a category, call search_products with only the category parameter (no query needed).
- The exact categories are: "electronics", "jewelery", "men's clothing", "women's clothing"
- Use get_categories if you're unsure what categories exist.
- If a search returns no results, try broadening: drop the query and just use category, or different keywords.
- The store has a small catalog (~20 products), so keep searches broad.
- Do NOT paste image URLs or product links in your text — the product cards already show images."""


class ShoppingAgent:
    """AI shopping assistant backed by a LangGraph stateful agent."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.llm = ChatOpenAI(
            model="gpt-4-turbo-preview",
            temperature=0.7,
            streaming=True,
            api_key=api_key,
        )

        self.tools = [
            search_products,
            get_product_details,
            get_categories,
            add_to_cart,
            get_cart,
            remove_from_cart,
        ]

        # Bind tools so the LLM can generate tool_calls
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # Build the state machine
        self.graph = self._build_graph()

    # ── Graph Construction ──

    def _build_graph(self):
        """
        Build a LangGraph StateGraph:

            START → agent → should_continue?
                              ├─ tool_calls → tools → agent
                              └─ done       → END
        """
        graph = StateGraph(AgentState)

        # Nodes
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", ToolNode(self.tools))

        # Entry point
        graph.set_entry_point("agent")

        # Conditional routing after the agent node
        graph.add_conditional_edges(
            "agent",
            self._should_continue,
            {"continue": "tools", "end": END},
        )

        # After tool execution, always loop back to the agent
        graph.add_edge("tools", "agent")

        return graph.compile()

    async def _agent_node(self, state: AgentState) -> dict:
        """LLM node — prepends system prompt, invokes model with tools."""
        messages = list(state["messages"])

        # Inject system prompt once at the beginning
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

        response = await self.llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    @staticmethod
    def _should_continue(state: AgentState) -> str:
        """Route: if the last message contains tool_calls → 'continue', else → 'end'."""
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "continue"
        return "end"

    # ── Streaming ──

    async def process_message(
        self,
        message: str,
        conversation_history: List[ChatMessage],
        conversation_id: str = "default",
        *,
        user_id: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Stream structured JSON events to the frontend."""
        import app.tools.shopping_tools as shopping_tools_module
        shopping_tools_module._context.conversation_id = conversation_id
        shopping_tools_module._context.user_id = user_id
        shopping_tools_module._context.last_search_ids = set()

        # Build message list from history
        chat_history: list[AnyMessage] = []
        for msg in conversation_history[-10:]:
            if msg.role == "user":
                chat_history.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                chat_history.append(AIMessage(content=msg.content))

        chat_history.append(HumanMessage(content=message))
        inputs: AgentState = {"messages": chat_history}

        try:
            full_response = ""
            sent_tool_starts: set[str] = set()

            async for msg, metadata in self.graph.astream(
                inputs, stream_mode="messages"
            ):
                if isinstance(msg, HumanMessage):
                    continue

                # AI text tokens
                if isinstance(msg, AIMessageChunk):
                    if msg.content:
                        full_response += msg.content
                        yield json.dumps({"type": "token", "content": msg.content})
                    continue

                # Tool results
                if isinstance(msg, ToolMessage) and msg.content:
                    tool_name = getattr(msg, "name", "") or ""

                    if tool_name and tool_name not in sent_tool_starts:
                        sent_tool_starts.add(tool_name)
                        yield json.dumps({"type": "tool_start", "tool": tool_name})

                    try:
                        parsed = json.loads(msg.content)
                        if tool_name == "search_products" and "products" in parsed:
                            yield json.dumps({"type": "products", "data": parsed["products"]})
                        elif tool_name == "get_product_details" and "id" in parsed:
                            yield json.dumps({"type": "product_detail", "data": parsed})
                        elif tool_name in ("get_cart", "add_to_cart", "remove_from_cart"):
                            yield json.dumps({"type": "cart", "data": parsed})
                    except (json.JSONDecodeError, TypeError):
                        pass
                    continue

                # Full AIMessage (non-chunked fallback)
                if isinstance(msg, AIMessage) and not isinstance(msg, AIMessageChunk):
                    if msg.content and msg.content != full_response:
                        remaining = msg.content[len(full_response):]
                        if remaining:
                            full_response = msg.content
                            yield json.dumps({"type": "token", "content": remaining})

            # Fallback if streaming produced nothing
            if not full_response:
                result = await self.graph.ainvoke(inputs)
                if "messages" in result:
                    for m in result["messages"]:
                        if isinstance(m, AIMessage) and m.content:
                            for word in m.content.split():
                                yield json.dumps({"type": "token", "content": word + " "})
        except Exception as e:
            yield json.dumps({
                "type": "token",
                "content": f"I apologize, but I encountered an error: {str(e)}",
            })


# Global agent instance (lazy initialization)
_agent_instance: Optional[ShoppingAgent] = None


def get_agent() -> ShoppingAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = ShoppingAgent()
    return _agent_instance
