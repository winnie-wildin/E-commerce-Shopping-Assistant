"use client"

import { useState, useRef, useCallback } from "react"
import { useSession } from "next-auth/react"
import { MessageList, Message, CartData } from "./MessageList"
import { MessageInput } from "./MessageInput"
import { Product } from "./ProductCard"
import { sendMessage, parseStream } from "@/lib/api"
import { ShoppingBag } from "lucide-react"
import { AuthButton } from "@/components/auth/AuthButton"

export function ChatInterface() {
  const { data: session } = useSession()
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [conversationId] = useState(() => `conv_${Date.now()}`)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const handleSend = useCallback(async (content: string) => {
    if (!content.trim() || isLoading) return
    setError(null)

    const userMsg: Message = {
      id: `msg_${Date.now()}_u`,
      role: "user",
      content: content.trim(),
    }
    const assistantMsg: Message = {
      id: `msg_${Date.now()}_a`,
      role: "assistant",
      content: "",
      products: [],
      isStreaming: true,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsLoading(true)

    try {
      abortRef.current = new AbortController()
      const userId = session?.user?.email || undefined
      const stream = await sendMessage(content, conversationId, abortRef.current.signal, userId)

      for await (const event of parseStream(stream)) {
        setMessages(prev => {
          const last = prev[prev.length - 1]
          if (last.role !== "assistant") return prev

          // Create a NEW message object — never mutate the existing one.
          // React strict mode calls this updater twice; mutations cause duplication.
          let updated: Message
          switch (event.type) {
            case "token":
              updated = { ...last, content: last.content + (event.content || ""), toolActivity: null }
              break
            case "tool_start":
              updated = { ...last, toolActivity: event.tool || null }
              break
            case "products":
              updated = { ...last, products: [...(last.products || []), ...(event.data || [])], toolActivity: null }
              break
            case "product_detail":
              // Replace any previous search results — the detail view is what the user wanted
              updated = { ...last, products: [event.data], toolActivity: null }
              break
            case "cart":
              updated = { ...last, cart: event.data as CartData, toolActivity: null }
              break
            default:
              return prev
          }
          return [...prev.slice(0, -1), updated]
        })
      }

      // Mark streaming complete (immutable update)
      setMessages(prev => {
        const last = prev[prev.length - 1]
        if (last.role === "assistant") {
          return [...prev.slice(0, -1), { ...last, isStreaming: false }]
        }
        return prev
      })
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return
      const errorMsg = err instanceof Error ? err.message : "Failed to send message"
      setError(errorMsg)
      // Remove empty assistant message on error
      setMessages(prev => {
        const last = prev[prev.length - 1]
        if (last?.role === "assistant" && !last.content) return prev.slice(0, -1)
        return prev
      })
    } finally {
      setIsLoading(false)
      abortRef.current = null
    }
  }, [isLoading, conversationId, session?.user?.email])

  const handleAddToCart = useCallback((productId: number, productTitle: string) => {
    handleSend(`Add "${productTitle}" (product #${productId}) to my cart`)
  }, [handleSend])

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border bg-card shadow-sm shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-primary/10">
            <ShoppingBag className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-foreground">Shopping Assistant</h1>
            <p className="text-xs text-muted-foreground">AI-powered product discovery</p>
          </div>
        </div>
        <AuthButton />
      </header>

      {/* Messages */}
      <MessageList
        messages={messages}
        isLoading={isLoading}
        onAddToCart={handleAddToCart}
        onSuggestionClick={handleSend}
      />

      {/* Error banner */}
      {error && (
        <div className="px-4 py-2 text-sm text-destructive bg-destructive/10 border-t border-destructive/20 shrink-0 flex items-center justify-between gap-2">
          <span>{error}</span>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setError(null)
                const lastUserMsg = messages.filter(m => m.role === "user").pop()
                if (lastUserMsg) {
                  handleSend(lastUserMsg.content)
                }
              }}
              className="px-2 py-1 text-xs rounded bg-destructive/20 hover:bg-destructive/30 transition-colors focus:outline-none focus:ring-2 focus:ring-destructive"
            >
              Retry
            </button>
            <button
              onClick={() => setError(null)}
              className="px-2 py-1 text-xs rounded hover:bg-destructive/20 transition-colors focus:outline-none focus:ring-2 focus:ring-destructive"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <MessageInput onSend={handleSend} isLoading={isLoading} />
    </div>
  )
}
