// Server-Sent Events parser for a fetch() body (we POST, so EventSource can't be used).
// Handles events split across network chunks, CRLF line endings, ": keep-alive" comments
// and multi-line data fields.

export interface RawEvent {
  event: string;
  data: string;
}

function parseBlock(block: string): RawEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue; // empty or comment (keep-alive)
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<RawEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n?/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const parsed = parseBlock(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        if (parsed) yield parsed;
      }
    }
    buffer += decoder.decode();
    const last = parseBlock(buffer.replace(/\r\n?/g, "\n").trim());
    if (last) yield last;
  } finally {
    reader.releaseLock();
  }
}
