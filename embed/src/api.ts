import { readSSE } from "./sse";
import type { ChatEvent, HistoryMessage } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number, // 0 = network error / offline
    message: string,
    public retryAfter?: number,
  ) {
    super(message);
  }
}

/** Host + path of the current page (never the query string: it can contain tokens or personal data). */
export function currentPage(): string {
  return window.location.hostname + window.location.pathname;
}

export function newClientMessageId(): string {
  if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
  const bytes = window.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export class ChatApi {
  constructor(private baseUrl: string) {}

  private async request(path: string, init: RequestInit = {}): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(this.baseUrl + path, {
        ...init,
        credentials: "include", // the httpOnly visitor cookie
        headers: { "Content-Type": "application/json", "X-Coltek-Page": currentPage(), ...(init.headers || {}) },
      });
    } catch {
      throw new ApiError(0, "network");
    }
    if (!response.ok) {
      let message = "";
      try {
        message = ((await response.json()) as { error?: string }).error || "";
      } catch {
        /* not JSON */
      }
      const retryAfter = Number(response.headers.get("Retry-After")) || undefined;
      throw new ApiError(response.status, message, retryAfter);
    }
    return response;
  }

  async createThread(): Promise<string> {
    const response = await this.request("/api/threads", { method: "POST", body: JSON.stringify({ page: currentPage() }) });
    return ((await response.json()) as { thread_id: string }).thread_id;
  }

  /** The thread's messages, or null if it no longer exists for this visitor (404). */
  async getMessages(threadId: string): Promise<HistoryMessage[] | null> {
    try {
      const response = await this.request(`/api/threads/${encodeURIComponent(threadId)}/messages`, { method: "GET" });
      return ((await response.json()) as { messages: HistoryMessage[] }).messages;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }

  async *sendMessage(
    args: { threadId: string; message: string; clientMessageId: string },
    signal: AbortSignal,
  ): AsyncGenerator<ChatEvent> {
    const response = await this.request("/api/chat", {
      method: "POST",
      signal,
      body: JSON.stringify({
        thread_id: args.threadId,
        message: args.message,
        page: currentPage(),
        client_message_id: args.clientMessageId,
      }),
    });
    if (!response.body) throw new ApiError(0, "network");
    try {
      for await (const raw of readSSE(response.body)) {
        let data: Record<string, unknown> = {};
        try {
          data = JSON.parse(raw.data);
        } catch {
          continue;
        }
        yield { type: raw.event, ...data } as ChatEvent;
      }
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if ((error as { name?: string }).name === "AbortError") throw error;
      throw new ApiError(0, "network"); // connection dropped mid-stream
    }
  }
}
