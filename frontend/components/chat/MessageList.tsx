"use client"

import { useEffect, useRef, useCallback, useState, ReactNode } from "react"
import { ProductCard, Product } from "./ProductCard"
import { Bot, User, ShoppingBag, ShoppingCart, ChevronDown, ChevronUp, Package, Sparkles, Search, Tag } from "lucide-react"

export interface CartItem {
  product_id: number
  title: string
  price: number
  quantity: number
  subtotal: number
}

export interface CartData {
  cart_id?: number
  items?: CartItem[]
  total?: number
  item_count?: number
  message?: string
  total_items?: number
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  products?: Product[]
  cart?: CartData
  isStreaming?: boolean
  toolActivity?: string | null
}

interface MessageListProps {
  messages: Message[]
  isLoading: boolean
  onAddToCart: (productId: number, productTitle: string) => void
  onSuggestionClick: (text: string) => void
}

const SUGGESTIONS = [
  { text: "Show me electronics", icon: Search },
  { text: "What categories do you have?", icon: Tag },
  { text: "Find me jewelry under $100", icon: Sparkles },
]

export function MessageList({ messages, isLoading, onAddToCart, onSuggestionClick }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const isNearBottomRef = useRef(true)

  // Track whether user is near the bottom of the scroll container
  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const threshold = 150 // px from bottom
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  }, [])

  // Only auto-scroll if user hasn't scrolled up to read
  useEffect(() => {
    if (isNearBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages])

  // Empty state
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center mb-5 shadow-sm">
          <ShoppingBag className="w-8 h-8 text-primary" />
        </div>
        <h2 className="text-2xl font-bold mb-2 tracking-tight">Shopping Assistant</h2>
        <p className="text-muted-foreground max-w-sm mb-8">
          Discover products, compare items, and manage your cart — all through conversation.
        </p>
        <div className="flex flex-col gap-2.5 text-sm w-full max-w-xs">
          {SUGGESTIONS.map(({ text, icon: Icon }) => (
            <button
              key={text}
              onClick={() => onSuggestionClick(text)}
              className="flex items-center gap-3 px-4 py-3 rounded-xl border border-border bg-card hover:bg-accent/50 hover:border-primary/30 transition-all text-left cursor-pointer shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                <Icon className="w-4 h-4 text-primary" />
              </div>
              <span className="text-secondary-foreground">{text}</span>
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto p-4 space-y-4 bg-[radial-gradient(circle_at_1px_1px,var(--border)_1px,transparent_0)] [background-size:24px_24px]">
      {messages.map(msg => (
        <div
          key={msg.id}
          className={`max-w-3xl mx-auto flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
        >
          {/* Assistant avatar */}
          {msg.role === "assistant" && (
            <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-primary/15 to-primary/5 flex items-center justify-center mt-1">
              <Bot className="w-4 h-4 text-primary" />
            </div>
          )}

          <div className={`max-w-[85%] sm:max-w-[75%] ${msg.role === "user" ? "" : ""}`}>
            {/* Tool activity indicator */}
            {msg.toolActivity && msg.isStreaming && (
              <div className="mb-1.5 flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
                <span className="inline-block w-3 h-3 border-2 border-primary/40 border-t-primary rounded-full animate-spin" />
                {toolLabel(msg.toolActivity)}
              </div>
            )}

            {/* Message bubble */}
            <div
              className={`rounded-2xl px-4 py-2.5 ${
                msg.role === "user"
                  ? "bg-primary text-primary-foreground rounded-br-sm"
                  : "bg-card border border-border text-card-foreground rounded-bl-sm shadow-sm"
              }`}
            >
              {msg.content ? (
                <FormattedText text={msg.content} />
              ) : msg.isStreaming ? (
                <TypingIndicator />
              ) : null}
            </div>

            {/* Product cards — collapsible when more than 1 */}
            {msg.products && msg.products.length > 0 && (
              <CollapsibleProducts
                products={msg.products}
                onAddToCart={onAddToCart}
                isStreaming={msg.isStreaming}
              />
            )}

            {/* Cart display */}
            {msg.cart && <CartDisplay cart={msg.cart} />}
          </div>

          {/* User avatar */}
          {msg.role === "user" && (
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center mt-1">
              <User className="w-4 h-4 text-primary-foreground" />
            </div>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}


// ── Collapsible Product Cards ──

function CollapsibleProducts({
  products,
  onAddToCart,
  isStreaming,
}: {
  products: Product[]
  onAddToCart: (productId: number, productTitle: string) => void
  isStreaming?: boolean
}) {
  // Single product (detail view) — always show inline, no collapse
  const isSingle = products.length === 1
  const [expanded, setExpanded] = useState(false)

  // Price range for the summary
  const prices = products.map(p => p.price)
  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const priceRange = minPrice === maxPrice
    ? `$${minPrice.toFixed(2)}`
    : `$${minPrice.toFixed(2)} – $${maxPrice.toFixed(2)}`

  if (isSingle) {
    return (
      <div className="mt-3">
        <ProductCard product={products[0]} onAddToCart={onAddToCart} />
      </div>
    )
  }

  return (
    <div className="mt-3">
      {/* Toggle button */}
      <button
        onClick={() => setExpanded(prev => !prev)}
        className="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-border bg-card hover:bg-accent/50 transition-colors text-sm shadow-sm cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10">
          <Package className="w-4 h-4 text-primary" />
        </div>
        <div className="flex-1 text-left">
          <span className="font-medium">
            {products.length} products found
          </span>
          <span className="text-muted-foreground ml-2 text-xs">
            {priceRange}
          </span>
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>

      {/* Expanded card grid */}
      {expanded && (
        <div className="mt-3 grid gap-3 grid-cols-1 sm:grid-cols-2 animate-in slide-in-from-top-2 duration-200">
          {products.map((product, i) => (
            <ProductCard
              key={`${product.id}-${i}`}
              product={product}
              onAddToCart={onAddToCart}
            />
          ))}
        </div>
      )}
    </div>
  )
}


function toolLabel(tool: string): string {
  const labels: Record<string, string> = {
    search_products: "Searching products…",
    get_product_details: "Fetching product details…",
    get_categories: "Looking up categories…",
    add_to_cart: "Adding to cart…",
    get_cart: "Loading cart…",
    remove_from_cart: "Removing from cart…",
  }
  return labels[tool] || `Running ${tool}…`
}

/** Simple markdown-like text formatting */
function FormattedText({ text }: { text: string }) {
  const lines = text.split("\n")

  return (
    <div className="text-sm leading-relaxed space-y-1">
      {lines.map((line, i) => (
        <p key={i} className={line.trim() === "" ? "h-2" : ""}>
          {formatInline(line)}
        </p>
      ))}
    </div>
  )
}

function formatInline(text: string): ReactNode[] {
  // Order matters: images first, then bold, then plain text
  // Regex captures: ![alt](url) and **bold**
  const parts = text.split(/(!\[.*?\]\(.*?\)|\*\*.*?\*\*)/g)
  return parts.map((part, i) => {
    // Markdown image: ![alt](url) — hide these since product cards already show images
    if (/^!\[.*?\]\(.*?\)$/.test(part)) {
      return null
    }
    // Bold text
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return <span key={i}>{part}</span>
  })
}

function TypingIndicator() {
  return (
    <div className="flex gap-1.5 py-1 px-1">
      <span className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "300ms" }} />
    </div>
  )
}

function CartDisplay({ cart }: { cart: CartData }) {
  if (cart.message && (!cart.items || cart.items.length === 0)) {
    return (
      <div className="mt-2 p-3 rounded-xl bg-secondary/50 text-sm border border-border">
        {cart.message}
      </div>
    )
  }

  return (
    <div className="mt-3 rounded-xl border border-border overflow-hidden shadow-sm bg-card">
      <div className="px-4 py-3 bg-gradient-to-r from-primary/5 to-transparent font-medium text-sm flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
          <ShoppingCart className="w-3.5 h-3.5 text-primary" />
        </div>
        Shopping Cart
        {cart.item_count !== undefined && (
          <span className="ml-auto text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">
            {cart.item_count} item{cart.item_count !== 1 ? "s" : ""}
          </span>
        )}
      </div>
      {cart.items?.map((item, i) => (
        <div key={i} className="px-4 py-3 border-t border-border flex items-center justify-between gap-4 text-sm">
          <div className="min-w-0">
            <span className="font-medium line-clamp-1">{item.title}</span>
            <span className="text-muted-foreground text-xs ml-1">×{item.quantity}</span>
          </div>
          <span className="font-semibold tabular-nums shrink-0">${item.subtotal.toFixed(2)}</span>
        </div>
      ))}
      {cart.total !== undefined && (
        <div className="px-4 py-3 border-t-2 border-primary/20 bg-gradient-to-r from-primary/10 to-primary/5 flex justify-between font-bold text-sm">
          <span>Total</span>
          <span className="text-primary text-base">${cart.total.toFixed(2)}</span>
        </div>
      )}
    </div>
  )
}
