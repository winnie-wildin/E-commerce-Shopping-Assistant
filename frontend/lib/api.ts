const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface StreamEvent {
  type: 'token' | 'products' | 'product_detail' | 'cart' | 'tool_start' | 'error';
  content?: string;
  data?: any;
  tool?: string;
}

export async function sendMessage(
  message: string,
  conversationId?: string,
  signal?: AbortSignal,
  userId?: string
): Promise<ReadableStream<Uint8Array>> {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(userId ? { 'X-User-Id': userId } : {}),
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
    }),
    signal,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `API error: ${response.statusText}`);
  }

  if (!response.body) {
    throw new Error('No response body');
  }

  return response.body;
}

export async function* parseStream(
  stream: ReadableStream<Uint8Array>
): AsyncGenerator<StreamEvent, void, unknown> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) continue;

        const data = trimmed.slice(6);
        if (data === '[DONE]') return;

        try {
          yield JSON.parse(data) as StreamEvent;
        } catch {
          // Fallback: treat as plain text token
          if (data) yield { type: 'token', content: data };
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
